const std = @import("std");
const l = std.os.linux;
const m = @import("../../metrics.zig");
const Ring = @import("../ring.zig").Ring;
const Workload = @import("../../workload.zig").Workload;
const protocol = @import("protocol.zig");
const chunk = 16384;
const Mode = enum { epoll, oneshot, multishot };
const Pattern = enum { uniform, burst, randomized };
const Config = struct {
    mode: Mode, n: usize, active: usize, payload: usize, rate: u64,
    duration_ns: u64, seed: u64, pattern: Pattern, batch: usize,
    consumer_cpu: usize, producer_cpu: usize,
};
fn pin(cpu: usize) !void {
    var set = std.mem.zeroes(l.cpu_set_t);
    const bits = @bitSizeOf(@TypeOf(set[0]));
    set[cpu / bits] |= @as(@TypeOf(set[0]), 1) << @intCast(cpu % bits);
    try l.sched_setaffinity(0, &set);
}
const Cpu = struct {
    user_us: u64, system_us: u64,
    fn get() Cpu {
        var usage: l.rusage = undefined;
        _ = m.check(l.getrusage(l.rusage.THREAD, &usage)) catch @panic("thread getrusage");
        return .{ .user_us = @intCast(usage.utime.sec * 1000000 + usage.utime.usec), .system_us = @intCast(usage.stime.sec * 1000000 + usage.stime.usec) };
    }
    fn diff(end: Cpu, start: Cpu) Cpu { return .{ .user_us = end.user_us - start.user_us, .system_us = end.system_us - start.system_us }; }
};
fn until(deadline: u64) void {
    while (true) {
        const now = m.now();
        if (now >= deadline) break;
        const left = deadline - now;
        if (left > 50000) {
            const ns = left - 20000;
            const delay: l.timespec = .{ .sec = @intCast(ns / 1000000000), .nsec = @intCast(ns % 1000000000) };
            _ = l.nanosleep(&delay, null);
        } else std.atomic.spinLoopHint();
    }
}
const Producer = struct {
    c: Config,
    w: *Workload,
    start: u64,
    sent: u64 = 0,
    bytes: u64 = 0,
    eagain: u64 = 0,
    calls: u64 = 0,
    late_sum_ns: u64 = 0,
    late_max_ns: u64 = 0,
    last_sent_ns: u64 = 0,
    cpu: Cpu = .{ .user_us = 0, .system_us = 0 },
    failed: bool = false,
    sequences: []u64,
    send_times: []u64,
    fn run(p: *Producer) void {
        defer for (p.w.pairs) |pair| { _ = l.shutdown(pair[1], 1); };
        p.body() catch |err| { p.failed = true; std.debug.print("producer: {s}\n", .{@errorName(err)}); };
    }
    fn body(p: *Producer) !void {
        try pin(p.c.producer_cpu);
        var prng = std.Random.DefaultPrng.init(p.c.seed ^ 0x12345678);
        const random = prng.random();
        const begin_cpu = Cpu.get();
        var data: [4096]u8 = undefined;
        var arrival = p.start;
        for (p.send_times, 0..) |*sent_at, message| {
            if (p.c.pattern != .randomized and message >= p.c.rate * p.c.duration_ns / 1000000000) break;
            switch (p.c.pattern) {
                .uniform => arrival = p.start + @as(u64, @intCast(message)) * 1000000000 / p.c.rate,
                .burst => arrival = p.start + @as(u64, @intCast(message / 32 * 32)) * 1000000000 / p.c.rate,
                .randomized => {
                    if (message > 0) {
                        const u = @max(random.float(f64), 0.000000001);
                        arrival += @intFromFloat(-@log(u) * 1000000000.0 / @as(f64, @floatFromInt(p.c.rate)));
                    }
                },
            }
            if (arrival >= p.start + p.c.duration_ns) break;
            until(arrival);
            const index = p.w.order[random.uintLessThan(usize, p.c.active)];
            const actual = m.now();
            const late = actual - arrival;
            p.late_sum_ns += late;
            p.late_max_ns = @max(p.late_max_ns, late);
            protocol.encode(data[0..p.c.payload], index, p.sequences[index], actual);
            var offset: usize = 0;
            while (offset < p.c.payload) {
                p.calls += 1;
                const raw = l.sendto(p.w.pairs[index][1], data[offset..].ptr, p.c.payload - offset, l.MSG.NOSIGNAL, null, 0);
                switch (l.errno(raw)) {
                    .SUCCESS => { if (raw == 0) return error.NoSendProgress; offset += raw; },
                    .INTR => continue,
                    .AGAIN => { p.eagain += 1; if (m.now() > p.start + p.c.duration_ns + 10000000000) return error.ProducerTimeout; std.atomic.spinLoopHint(); },
                    else => return error.SendFailed,
                }
            }
            sent_at.* = actual;
            p.sent += 1;
            p.bytes += p.c.payload;
            p.sequences[index] += 1;
            p.last_sent_ns = m.now();
        }
        p.cpu = Cpu.diff(Cpu.get(), begin_cpu);
    }
};
const Latencies = struct {
    items: []u64,
    count: usize = 0,
    pub fn append(s: *Latencies, value: u64) !void {
        if (s.count == s.items.len) return error.LatencyCapacity;
        s.items[s.count] = value;
        s.count += 1;
    }
    fn percentile(s: *Latencies, percent: usize) u64 {
        if (s.count == 0) return 0;
        return s.items[@min(s.count - 1, (s.count - 1) * percent / 100)];
    }
};
const Counters = struct { waits: u64 = 0, recvs: u64 = 0, eagain: u64 = 0, cqes: u64 = 0, rearms: u64 = 0, enobufs: u64 = 0, recycle_ns: u64 = 0, recycled: u64 = 0, peak_cq: u32 = 0, eof: u64 = 0 };
pub fn main(init: std.process.Init) !void {
    const a = init.gpa;
    const args = try init.minimal.args.toSlice(init.arena.allocator());
    if (args.len != 13) return error.Usage_backend_fds_active_payload_rate_duration_ms_seed_pattern_batch_consumerCPU_producerCPU_sendTimes;
    const c: Config = .{
        .mode = std.meta.stringToEnum(Mode, args[1]) orelse return error.BadMode,
        .n = try std.fmt.parseInt(usize, args[2], 10),
        .active = try std.fmt.parseInt(usize, args[3], 10),
        .payload = try std.fmt.parseInt(usize, args[4], 10),
        .rate = try std.fmt.parseInt(u64, args[5], 10),
        .duration_ns = (try std.fmt.parseInt(u64, args[6], 10)) * 1000000,
        .seed = try std.fmt.parseInt(u64, args[7], 10),
        .pattern = std.meta.stringToEnum(Pattern, args[8]) orelse return error.BadPattern,
        .batch = try std.fmt.parseInt(usize, args[9], 10),
        .consumer_cpu = try std.fmt.parseInt(usize, args[10], 10),
        .producer_cpu = try std.fmt.parseInt(usize, args[11], 10),
    };
    if (c.n == 0 or c.n > 4096 or c.active > c.n or c.payload < 24 or c.payload > 4096 or c.rate == 0 or c.batch == 0 or c.batch > 256) return error.InvalidConfig;
    try pin(c.consumer_cpu);
    const life_start = m.now();
    var w = try Workload.init(a, c.n, c.seed);
    defer w.deinit();
    const capacity: usize = @intCast(c.rate * c.duration_ns / 1000000000 * 2 + 1024);
    const latency_storage = try a.alloc(u64, capacity);
    defer a.free(latency_storage);
    var latencies: Latencies = .{ .items = latency_storage };
    const send_times = try a.alloc(u64, if (c.active > 0) capacity else 0);
    defer a.free(send_times);
    const sequences = try a.alloc(u64, c.n);
    defer a.free(sequences);
    @memset(sequences, 0);
    const parser_storage = try a.alloc(u8, c.n * c.payload);
    defer a.free(parser_storage);
    const parsers = try a.alloc(protocol.Parser, c.n);
    defer a.free(parsers);
    for (parsers, 0..) |*p, i| p.* = .{ .storage = parser_storage[i * c.payload ..][0..c.payload], .index = i };
    const pending = try a.alloc(bool, c.n);
    defer a.free(pending);
    @memset(pending, false);
    const closed = try a.alloc(bool, c.n);
    defer a.free(closed);
    @memset(closed, false);
    const buffers = try a.alloc(u8, if (c.mode == .oneshot) c.n * chunk else chunk);
    defer a.free(buffers);
    var events: [256]l.epoll_event = undefined;
    var cq: [256]l.io_uring_cqe = undefined;
    var ring: Ring = undefined;
    var group: l.IoUring.BufferGroup = undefined;
    var ep: l.fd_t = -1;
    var counters: Counters = .{};
    const backend_start = m.now();
    if (c.mode == .epoll) {
        ep = @intCast(try m.check(l.epoll_create1(l.EPOLL.CLOEXEC)));
        for (w.pairs, 0..) |p, i| {
            var ev: l.epoll_event = .{ .events = l.EPOLL.IN | l.EPOLL.RDHUP, .data = .{ .u64 = i } };
            _ = try m.check(l.epoll_ctl(ep, l.EPOLL.CTL_ADD, p[0], &ev));
        }
    } else {
        ring = try Ring.init(256, 16384);
        if (c.mode == .multishot) group = @import("buffers.zig").init(&ring.u, a, chunk, 4096) catch |err| { ring.deinit(); return err; };
        for (0..c.n) |i| queue(c, &ring, &group, &w, buffers, pending, i) catch @panic("initial queue");
        ring.flush() catch @panic("initial submission");
    }
    const backend_init_ns = m.now() - backend_start;
    // Fatal validation/syscall failures intentionally abort without releasing live
    // kernel buffers. Normal shutdown drains EOF terminal CQEs for every socket.
    const start = m.now() + 20000000;
    var producer: Producer = .{ .c = c, .w = &w, .start = start, .sequences = sequences, .send_times = send_times };
    const process_before = m.Cpu.get();
    const cpu_before = Cpu.get();
    const thread = std.Thread.spawn(.{}, Producer.run, .{&producer}) catch @panic("producer spawn");
    var received: u64 = 0;
    var window_messages: u64 = 0;
    var last_completion = start;
    var eof_count: usize = 0;
    while (eof_count < c.n) {
        if (m.now() > start + c.duration_ns + 15000000000) {
            std.debug.print("watchdog: received={d} EOF={d}/{d} pending=", .{received, eof_count, c.n});
            for (pending, 0..) |p, i| if (p) { std.debug.print("{d},", .{i}); };
            std.debug.print("\n", .{});
            @panic("consumer watchdog");
        }
        if (c.mode == .epoll) {
            counters.waits += 1;
            const n = m.check(l.epoll_wait(ep, &events, events.len, 100)) catch |err| {
                if (err == error.Interrupted) continue;
                @panic("epoll_wait");
            };
            for (events[0..n]) |ev| {
                const i: usize = @intCast(ev.data.u64);
                if (closed[i]) continue;
                var budget: usize = 0;
                while (budget < 65536) {
                    counters.recvs += 1;
                    const raw = l.recvfrom(w.pairs[i][0], buffers.ptr, chunk, 0, null, null);
                    switch (l.errno(raw)) {
                        .SUCCESS => {
                            if (raw == 0) {
                                closed[i] = true; eof_count += 1;
                                _ = m.check(l.epoll_ctl(ep, l.EPOLL.CTL_DEL, w.pairs[i][0], null)) catch @panic("DEL on EOF");
                                break;
                            }
                            const count = parsers[i].feed(buffers[0..raw], 0, &latencies) catch @panic("record validation");
                            received += count;
                            last_completion = m.now();
                            if (last_completion <= start + c.duration_ns) window_messages += count;
                            budget += raw;
                        },
                        .INTR => continue,
                        .AGAIN => { counters.eagain += 1; break; },
                        else => @panic("recv failure"),
                    }
                }
            }
        } else {
            counters.peak_cq = @max(counters.peak_cq, ring.u.cq_ready());
            if (ring.u.cq_ready() == 0) boundedWait(&ring) catch @panic("bounded CQ wait");
            const n = ring.copy(&cq, false) catch @panic("CQ retrieval/overflow");
            var rearm: [256]usize = undefined;
            var rearm_count: usize = 0;
            for (cq[0..n]) |completion| {
                counters.cqes += 1;
                const i: usize = @intCast(completion.user_data);
                if (i >= c.n or !pending[i]) @panic("unexpected completion");
                const terminal = completion.flags & l.IORING_CQE_F_MORE == 0;
                if (terminal) pending[i] = false;
                if (completion.res > 0) {
                    const data = if (c.mode == .multishot) group.get(completion) catch @panic("buffer id") else buffers[i * chunk ..][0..@intCast(completion.res)];
                    const count = parsers[i].feed(data, 0, &latencies) catch @panic("record validation");
                    received += count;
                    last_completion = m.now();
                    if (last_completion <= start + c.duration_ns) window_messages += count;
                } else if (completion.res == 0) {
                    if (!terminal) @panic("EOF must terminate multishot");
                    closed[i] = true; eof_count += 1;
                } else {
                    if (!terminal) @panic("error without termination");
                    const err = -completion.res;
                    if (err == @backingInt(l.E.NOBUFS)) counters.enobufs += 1 else if (err == @backingInt(l.E.AGAIN)) counters.eagain += 1 else if (err != @backingInt(l.E.INTR)) @panic("CQE error");
                }
                if (c.mode == .multishot and completion.flags & l.IORING_CQE_F_BUFFER != 0) {
                    const recycle_start = m.now();
                    group.put(completion) catch @panic("buffer recycling");
                    counters.recycle_ns += m.now() - recycle_start;
                    counters.recycled += 1;
                }
                if (terminal and !closed[i]) { rearm[rearm_count] = i; rearm_count += 1; }
            }
            for (rearm[0..rearm_count]) |i| {
                queue(c, &ring, &group, &w, buffers, pending, i) catch @panic("rearm");
                counters.rearms += 1;
            }
            ring.flush() catch @panic("flush");
        }
    }
    const end = m.now();
    const consumer_cpu = Cpu.diff(Cpu.get(), cpu_before);
    thread.join();
    const process_after = m.Cpu.get();
    if (producer.failed or producer.sent != received or received != latencies.count) @panic("count mismatch");
    for (parsers, 0..) |p, i| if (p.used != 0 or p.sequence != sequences[i]) @panic("truncated stream");
    counters.eof = eof_count;
    var enters: u64 = 0;
    var submitted: u64 = 0;
    const destroy_start = m.now();
    if (c.mode == .epoll) { _ = l.close(ep); } else {
        for (pending) |p| if (p) @panic("live receive at teardown");
        try ring.healthy();
        enters = ring.enters;
        submitted = ring.submitted;
        if (c.mode == .multishot) group.deinit(a);
        ring.deinit();
    }
    const destroy_ns = m.now() - destroy_start;
    std.mem.sort(u64, latencies.items[0..latencies.count], {}, std.sort.asc(u64));
    // Output after timing. Optional per-message send-time sidecar is equally
    // populated in all modes and must be saved by performance runners.
    if (!std.mem.eql(u8, args[12], "-")) {
        const fd: l.fd_t = @intCast(try m.check(l.open(args[12], .{ .ACCMODE = .WRONLY, .CREAT = true, .TRUNC = true }, 0o600)));
        defer _ = l.close(fd);
        const bytes = std.mem.sliceAsBytes(send_times[0..producer.sent]);
        var offset: usize = 0;
        while (offset < bytes.len) offset += try m.check(l.write(fd, bytes[offset..].ptr, bytes.len - offset));
    }
    const ns = @max(end, start + c.duration_ns) - start;
    const json = try std.json.Stringify.valueAlloc(a, .{
        .config = c, .sent = producer.sent, .received = received, .bytes_received = producer.bytes,
        .window_messages = window_messages, .duration_ns = ns, .drain_ns = end -| (start + c.duration_ns),
        .last_completion_ns = last_completion -| start, .messages_s = @as(f64, @floatFromInt(received)) * 1e9 / @as(f64, @floatFromInt(ns)),
        .p50_ns = latencies.percentile(50), .p95_ns = latencies.percentile(95), .p99_ns = latencies.percentile(99),
        .consumer_cpu = consumer_cpu, .producer_cpu = producer.cpu,
        .process_user_us = process_after.user - process_before.user, .process_system_us = process_after.system - process_before.system,
        .backend_init_ns = backend_init_ns, .backend_destroy_ns = destroy_ns, .lifecycle_ns = m.now() - life_start,
        .producer_send_calls = producer.calls, .producer_eagain = producer.eagain,
        .producer_late_sum_ns = producer.late_sum_ns, .producer_late_max_ns = producer.late_max_ns,
        .producer_last_send_ns = producer.last_sent_ns -| start, .enters = enters, .sqes = submitted, .counters = counters,
    }, .{});
    defer a.free(json);
    try std.Io.File.stdout().writeStreamingAll(init.io, json);
    try std.Io.File.stdout().writeStreamingAll(init.io, "\n");
}
fn queue(c: Config, r: *Ring, group: *l.IoUring.BufferGroup, w: *Workload, buffers: []u8, pending: []bool, i: usize) !void {
    if (pending[i]) return error.DuplicateReceive;
    if (r.u.sq.sqe_tail -% r.u.sq.sqe_head >= 256) try r.flush();
    if (c.mode == .multishot) {
        _ = try group.recv_multishot(i, w.pairs[i][0], 0);
    } else {
        _ = try r.u.recv(i, w.pairs[i][0], .{ .buffer = buffers[i * chunk ..][0..chunk] }, 0);
    }
    pending[i] = true;
    if (r.u.sq.sqe_tail -% r.u.sq.sqe_head >= c.batch) try r.flush();
}
fn boundedWait(r: *Ring) !void {
    var ts: l.kernel_timespec = .{ .sec = 0, .nsec = 100000000 };
    var arg: l.io_uring_getevents_arg = .{ .sigmask = 0, .sigmask_sz = 0, .pad = 0, .ts = @intFromPtr(&ts) };
    r.enters += 1;
    const raw = l.syscall6(.io_uring_enter, @intCast(r.u.fd), 0, 1, l.IORING_ENTER_GETEVENTS | l.IORING_ENTER_EXT_ARG, @intFromPtr(&arg), @sizeOf(l.io_uring_getevents_arg));
    switch (l.errno(raw)) {
        .SUCCESS, .TIME, .INTR => {},
        else => return error.EnterFailed,
    }
}
