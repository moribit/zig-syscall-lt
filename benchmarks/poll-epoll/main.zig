const std = @import("std");
const m = @import("metrics.zig");
const W = @import("workload.zig").Workload;
const Poll = @import("poll.zig").Poll;
const Epoll = @import("epoll.zig").Epoll;
fn number(s: []const u8) !usize {
    return std.fmt.parseInt(usize, s, 10);
}
pub fn main(init: std.process.Init) !void {
    const args = try init.minimal.args.toSlice(init.arena.allocator());
    if (args.len != 8) return error.Usage_backend_mode_fds_ready_payload_iterations_seed;
    const is_epoll = std.mem.eql(u8, args[1], "epoll");
    if (!is_epoll and !std.mem.eql(u8, args[1], "poll")) return error.BadBackend;
    const readiness = std.mem.eql(u8, args[2], "readiness");
    if (!readiness and !std.mem.eql(u8, args[2], "receive")) return error.BadMode;
    const n = try number(args[3]);
    const ready = try number(args[4]);
    const payload = try number(args[5]);
    const rounds = try number(args[6]);
    const seed = try number(args[7]);
    if (n == 0 or ready > n or (payload != 64 and payload != 1024) or rounds == 0 or (!readiness and ready == 0)) return error.InvalidCondition;
    var w = try W.init(init.gpa, n, seed);
    defer w.deinit();
    var p: Poll = undefined;
    var e: Epoll = undefined;
    const setup_start = m.now();
    if (is_epoll) e = try Epoll.init(init.gpa, w.pairs) else p = try Poll.init(init.gpa, w.pairs);
    defer {
        if (is_epoll) e.deinit() else p.deinit();
    }
    const setup_ns = m.now() - setup_start;
    const indices = try init.gpa.alloc(usize, n);
    defer init.gpa.free(indices);
    const received = try init.gpa.alloc(usize, n);
    defer init.gpa.free(received);
    const expected = try init.gpa.alloc(bool, n);
    defer init.gpa.free(expected);
    const seen = try init.gpa.alloc(bool, n);
    defer init.gpa.free(seen);
    @memset(expected, false);
    for (w.order[0..ready]) |i| expected[i] = true;
    var stats: m.Stats = .{};
    var duration: u64 = 0;
    var user: u64 = 0;
    var system: u64 = 0;
    var events: u64 = 0;
    var bytes: u64 = 0;
    var sent: u64 = 0;
    var calls_ns: u64 = 0;
    var e2e_duration: u64 = 0;
    var producer_ns: u64 = 0;
    var e2e_user: u64 = 0;
    var e2e_system: u64 = 0;
    if (readiness) sent = try w.fill(ready, payload, 0, &stats);
    for (0..rounds) |round| {
        if (!readiness) @memset(received, 0);
        const full_cpu0 = if (!readiness) m.Cpu.get() else m.Cpu{ .user = 0, .system = 0 };
        const full_begin = if (!readiness) m.now() else 0;
        if (!readiness) {
            sent += try w.fill(ready, payload, round, &stats);
            producer_ns += m.now() - full_begin;
        }
        const cpu0 = m.Cpu.get();
        const begin = m.now();
        if (readiness) {
            const t = m.now();
            const count = if (is_epoll) try e.wait(indices, 0, &stats) else try p.wait(indices, 0, &stats);
            calls_ns += m.now() - t;
            events += count;
            if (count != ready) return error.WrongReadyCount;
            // Inspect the full set, not just count. Validation is outside the
            // acquisition interval, but inside duration_ns for both backends.
            @memset(seen, false);
            for (indices[0..count]) |i| {
                if (!expected[i] or seen[i]) return error.WrongReadySet;
                seen[i] = true;
            }
        } else {
            var total: usize = 0;
            while (total < ready * payload) {
                if (m.now() - begin > 5_000_000_000) return error.ConsumerTimeout;
                const t = m.now();
                const count = if (is_epoll) try e.wait(indices, 0, &stats) else try p.wait(indices, 0, &stats);
                calls_ns += m.now() - t;
                events += count;
                for (indices[0..count]) |i| {
                    if (!expected[i] or received[i] >= payload) return error.UnexpectedReady;
                    const got = try w.receive(i, payload - received[i], @intCast(round % 251), &stats);
                    received[i] += got;
                    total += got;
                }
            }
            bytes += total;
            for (w.order[0..ready]) |i| if (received[i] != payload) return error.MissingData;
        }
        const end = m.now();
        duration += end - begin;
        if (!readiness) e2e_duration += end - full_begin;
        const cpu1 = m.Cpu.get();
        user += cpu1.user - cpu0.user;
        system += cpu1.system - cpu0.system;
        if (!readiness) {
            e2e_user += cpu1.user - full_cpu0.user;
            e2e_system += cpu1.system - full_cpu0.system;
        }
    }
    if (!readiness and bytes != sent) return error.ByteCountMismatch;
    var buffer: [2048]u8 = undefined;
    const line = try std.fmt.bufPrint(&buffer, "{{\"backend\":\"{s}\",\"benchmark\":\"{s}\",\"fds\":{d},\"ready_fds\":{d},\"payload\":{d},\"iterations\":{d},\"duration_ns\":{d},\"acquisition_ns\":{d},\"events_observed\":{d},\"bytes_received\":{d},\"bytes_sent\":{d},\"messages\":{d},\"user_us\":{d},\"system_us\":{d},\"wait_calls\":{d},\"recv_calls\":{d},\"send_calls\":{d},\"eintr\":{d},\"eagain\":{d},\"errors\":{d},\"setup_ns\":{d},\"e2e_duration_ns\":{d},\"producer_ns\":{d},\"e2e_user_us\":{d},\"e2e_system_us\":{d}}}\n", .{ args[1], args[2], n, ready, payload, rounds, duration, calls_ns, events, bytes, sent, if (readiness) @as(usize, 0) else ready * rounds, user, system, stats.wait_calls, stats.recv_calls, stats.send_calls, stats.eintr, stats.eagain, stats.errors, setup_ns, e2e_duration, producer_ns, e2e_user, e2e_system });
    try std.Io.File.stdout().writeStreamingAll(init.io, line);
}
