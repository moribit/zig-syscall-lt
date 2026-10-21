const std = @import("std");
const m = @import("../metrics.zig");
const l = m.l;
const Workload = @import("../workload.zig").Workload;
const Poll = @import("../poll.zig").Poll;
const Epoll = @import("../epoll.zig").Epoll;
const Receiver = @import("recv.zig").Receiver;
pub fn main(init: std.process.Init) !void {
    const a = init.gpa;
    const args = try init.minimal.args.toSlice(init.arena.allocator());
    if (args.len != 10) return error.Usage;
    const backend = args[1];
    const n = try std.fmt.parseInt(usize, args[2], 10);
    const ready = try std.fmt.parseInt(usize, args[3], 10);
    const payload = try std.fmt.parseInt(usize, args[4], 10);
    const bursts = try std.fmt.parseInt(usize, args[5], 10);
    const seed = try std.fmt.parseInt(u64, args[6], 10);
    const batch = try std.fmt.parseInt(usize, args[7], 10);
    const capacity = try std.fmt.parseInt(u16, args[8], 10);
    const cq_batch = try std.fmt.parseInt(usize, args[9], 10);
    const uring = std.mem.eql(u8, backend, "uring");
    const uring_poll = std.mem.eql(u8, backend, "uring-poll");
    const poll = std.mem.eql(u8, backend, "poll");
    const epoll = std.mem.eql(u8, backend, "epoll");
    if (!(uring or uring_poll or poll or epoll) or n == 0 or ready > n or payload == 0 or payload > 1024 or bursts == 0 or batch == 0 or cq_batch == 0 or capacity == 0) return error.BadArguments;
    const lifetime_cpu0 = m.Cpu.get();
    const w0 = m.now();
    var w = try Workload.init(a, n, seed);
    defer w.deinit();
    const workload_ns = m.now() - w0;
    const start_init = m.now();
    var p: ?Poll = if (poll) try Poll.init(a, w.pairs) else null;
    defer if (p) |*v| v.deinit();
    var e: ?Epoll = if (epoll) try Epoll.init(a, w.pairs) else null;
    defer if (e) |*v| v.deinit();
    var r: ?Receiver = if (uring or uring_poll) try Receiver.init(a, w.pairs, payload, capacity, batch, uring_poll) else null;
    // Must drain BEFORE freeing w, buffers, or ring, including error unwinding.
    defer if (r) |*v| v.deinit();
    const backend_init_ns = m.now() - start_init;
    const setup_ns = if (r) |v| v.ring.setup_ns else 0;
    const mmap_ns = if (r) |v| v.ring.mmap_ns else 0;
    const allocation_ns = if (r) |v| v.allocation_ns else 0;
    const initial_submit_ns = if (r) |v| v.initial_submit_ns else 0;
    const initial_enter_calls = if (r) |v| v.ring.enters else 0;
    const offsets = try a.alloc(usize, n);
    defer a.free(offsets);
    const events = try a.alloc(usize, n);
    defer a.free(events);
    const cq = try a.alloc(l.io_uring_cqe, cq_batch);
    defer a.free(cq);
    var stats: m.Stats = .{};
    var total_ns: u64 = 0;
    var producer_ns: u64 = 0;
    var consumer_ns: u64 = 0;
    var submit_ns: u64 = 0;
    var wait_ns: u64 = 0;
    var first_completion_ns: u64 = 0;
    var messages: u64 = 0;
    var received: u64 = 0;
    var sent: u64 = 0;
    var completion_count: u64 = 0;
    const cpu0 = m.Cpu.get();
    for (0..bursts) |round| {
        @memset(offsets, 0);
        var done: usize = 0;
        const begin = m.now();
        sent += try w.fill(ready, payload, round, &stats);
        const consume_start = m.now();
        producer_ns += consume_start - begin;
        const deadline = consume_start + 10_000_000_000;
        while (done < ready) {
            if (m.now() > deadline) return error.ConsumerTimeout;
            const wait0 = m.now();
            if (r) |*v| {
                // Read CQ without blocking; bounded busy waiting matches timeout=0
                // on poll/epoll and gives the benchmark a watchdog.
                const count = try v.ring.copy(cq, false);
                wait_ns += m.now() - wait0;
                completion_count += count;
                var rearm: usize = 0;
                for (cq[0..count]) |c| {
                    if (c.flags != 0) return error.UnexpectedCqeFlags;
                    const i: usize = @intCast(c.user_data);
                    if (i >= n or !v.pending[i] or offsets[i] >= payload) return error.InvalidCompletion;
                    v.pending[i] = false;
                    if (first_completion_ns == 0) first_completion_ns = m.now() - begin;
                    if (c.res < 0) {
                        if (c.res == -@as(i32, @backingInt(l.E.AGAIN))) stats.eagain += 1 else if (c.res == -@as(i32, @backingInt(l.E.INTR))) stats.eintr += 1 else return error.NegativeCompletion;
                    } else if (uring_poll) {
                        if (@as(u32, @intCast(c.res)) & (l.POLL.IN | l.POLL.ERR | l.POLL.HUP) == 0) return error.InvalidPollMask;
                        const got = try w.receive(i, payload - offsets[i], @intCast(round % 251), &stats);
                        offsets[i] += got;
                        received += got;
                    } else {
                        if (c.res == 0) return error.UnexpectedEof;
                        const got: usize = @intCast(c.res);
                        if (got > payload - offsets[i]) return error.ExcessBytes;
                        for (v.buffers[i * payload + offsets[i] ..][0..got]) |byte| if (byte != round % 251) return error.CorruptData;
                        offsets[i] += got;
                        received += got;
                    }
                    const full = offsets[i] == payload;
                    if (full) {
                        done += 1;
                        messages += 1;
                    }
                    if (!full or round + 1 < bursts) {
                        events[rearm] = i;
                        rearm += 1;
                    }
                }
                const submit0 = m.now();
                for (events[0..rearm]) |i| try v.queue(i, if (offsets[i] == payload) 0 else offsets[i]);
                try v.ring.flush();
                submit_ns += m.now() - submit0;
            } else {
                const count = if (p) |*v| try v.wait(events, 0, &stats) else try e.?.wait(events, 0, &stats);
                wait_ns += m.now() - wait0;
                if (count > 0 and first_completion_ns == 0) first_completion_ns = m.now() - begin;
                for (events[0..count]) |i| {
                    if (offsets[i] >= payload) return error.DuplicateMessage;
                    const got = try w.receive(i, payload - offsets[i], @intCast(round % 251), &stats);
                    offsets[i] += got;
                    received += got;
                    if (offsets[i] == payload) {
                        done += 1;
                        messages += 1;
                    }
                }
            }
        }
        const end = m.now();
        consumer_ns += end - consume_start;
        total_ns += end - begin;
        std.mem.rotate(usize, w.order, 1);
    }
    const cpu1 = m.Cpu.get();
    if (sent != received or messages != ready * bursts or received != ready * payload * bursts) return error.Accounting;
    const enter_calls = if (r) |v| v.ring.enters - initial_enter_calls else 0;
    const copies = if (r) |v| v.ring.copies else 0;
    const submitted = if (r) |v| v.ring.submitted else 0;
    const teardown0 = m.now();
    const before_finish = if (r) |v| v.ring.enters else 0;
    if (r) |*v| try v.finish();
    const cancel_ns = m.now() - teardown0;
    const finish_enters = if (r) |v| v.ring.enters - before_finish else 0;
    const destroy0 = m.now();
    if (r) |*v| {
        v.ring.deinit();
        a.free(v.buffers);
        a.free(v.pending);
    }
    r = null;
    if (e) |*v| v.deinit();
    e = null;
    if (p) |*v| v.deinit();
    p = null;
    const destroy_ns = m.now() - destroy0;
    const lifetime_cpu1 = m.Cpu.get();
    var buf: [8192]u8 = undefined;
    const text = try std.fmt.bufPrint(&buf, "{{\"status\":\"OK\",\"e2e_ns\":{d},\"producer_ns\":{d},\"consumer_ns\":{d},\"submit_ns\":{d},\"wait_ns\":{d},\"first_completion_ns\":{d},\"workload_setup_ns\":{d},\"backend_init_ns\":{d},\"ring_setup_ns\":{d},\"mmap_ns\":{d},\"buffer_allocation_ns\":{d},\"initial_submit_ns\":{d},\"cancel_ns\":{d},\"destroy_ns\":{d},\"user_us\":{d},\"system_us\":{d},\"messages\":{d},\"bytes_sent\":{d},\"bytes_received\":{d},\"wait_calls\":{d},\"recv_calls\":{d},\"send_calls\":{d},\"enter_calls\":{d},\"initial_enter_calls\":{d},\"finish_enter_calls\":{d},\"cq_copy_calls\":{d},\"sqes_submitted_including_initial\":{d},\"cqes\":{d},\"eagain\":{d},\"eintr\":{d},\"lifetime_user_us\":{d},\"lifetime_system_us\":{d},\"errors\":0}}\n", .{ total_ns, producer_ns, consumer_ns, submit_ns, wait_ns, first_completion_ns, workload_ns, backend_init_ns, setup_ns, mmap_ns, allocation_ns, initial_submit_ns, cancel_ns, destroy_ns, cpu1.user - cpu0.user, cpu1.system - cpu0.system, messages, sent, received, stats.wait_calls, stats.recv_calls, stats.send_calls, enter_calls, initial_enter_calls, finish_enters, copies, submitted, completion_count, stats.eagain, stats.eintr, lifetime_cpu1.user - lifetime_cpu0.user, lifetime_cpu1.system - lifetime_cpu0.system });
    try std.Io.File.stdout().writeStreamingAll(init.io, text);
}
