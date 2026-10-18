const std = @import("std");
const t = std.testing;
const m = @import("metrics.zig");
const l = m.l;
const W = @import("workload.zig").Workload;
const Poll = @import("poll.zig").Poll;
const Epoll = @import("epoll.zig").Epoll;

test "same ready sets, zero/all ready, LT repeated notifications, partial receive and EAGAIN" {
    for ([_]usize{ 1, 8, 64 }) |n| {
        var w = try W.init(t.allocator, n, 17);
        defer w.deinit();
        var p = try Poll.init(t.allocator, w.pairs);
        defer p.deinit();
        var e = try Epoll.init(t.allocator, w.pairs);
        defer e.deinit();
        var a: [64]usize = undefined;
        var b: [64]usize = undefined;
        var stats: m.Stats = .{};
        try t.expectEqual(@as(usize, 0), try p.wait(&a, 0, &stats));
        try t.expectEqual(@as(usize, 0), try e.wait(&b, 0, &stats));
        try t.expectEqual(@as(usize, 0), try w.receive(0, 64, 0, &stats));
        try t.expectEqual(@as(u64, 1), stats.eagain);
        _ = try w.fill(n, 64, 3, &stats);
        for (0..2) |_| {
            try t.expectEqual(n, try p.wait(&a, 0, &stats));
            try t.expectEqual(n, try e.wait(&b, 0, &stats));
            std.mem.sort(usize, a[0..n], {}, std.sort.asc(usize));
            std.mem.sort(usize, b[0..n], {}, std.sort.asc(usize));
            try t.expectEqualSlices(usize, a[0..n], b[0..n]);
        }
        for (0..n) |i| {
            try t.expectEqual(@as(usize, 32), try w.receive(i, 32, 3, &stats));
            try t.expectEqual(@as(usize, 32), try w.receive(i, 32, 3, &stats));
        }
        try t.expectEqual(@as(usize, 0), try p.wait(&a, 0, &stats));
        try t.expectEqual(@as(usize, 0), try e.wait(&b, 0, &stats));
    }
}

test "producer shutdown, data drained before EOF, HUP, unregister and resource closure" {
    var w = try W.init(t.allocator, 1, 1);
    const closed = w.pairs[0][0];
    {
        defer w.deinit();
        var p = try Poll.init(t.allocator, w.pairs);
        defer p.deinit();
        var e = try Epoll.init(t.allocator, w.pairs);
        defer e.deinit();
        var stats: m.Stats = .{};
        var out: [1]usize = undefined;
        _ = try w.fill(1, 64, 7, &stats);
        _ = try m.check(l.shutdown(w.pairs[0][1], l.SHUT.WR));
        try t.expectEqual(@as(usize, 1), try p.wait(&out, 0, &stats));
        try t.expectEqual(@as(usize, 1), try e.wait(&out, 0, &stats));
        try t.expectEqual(@as(usize, 64), try w.receive(0, 64, 7, &stats));
        try t.expectError(error.UnexpectedEof, w.receive(0, 64, 7, &stats));
        // EOF stays readable under LT; it must be consumed/removed by caller.
        try t.expectEqual(@as(usize, 1), try e.wait(&out, 0, &stats));
        try p.remove(0);
        try e.remove(w.pairs[0][0]);
        try t.expectEqual(@as(usize, 0), try p.wait(&out, 0, &stats));
        try t.expectEqual(@as(usize, 0), try e.wait(&out, 0, &stats));
        try t.expectError(error.SyscallFailed, e.remove(w.pairs[0][0]));
    }
    var byte: [1]u8 = undefined;
    try t.expectEqual(l.E.BADF, l.errno(l.read(closed, &byte, 1)));
}

fn handler(_: l.SIG) callconv(.c) void {}
fn interrupt(pid: l.pid_t, tid: l.pid_t) void {
    const delay: l.timespec = .{ .sec = 0, .nsec = 20_000_000 };
    _ = l.nanosleep(&delay, null);
    _ = l.tgkill(pid, tid, .USR1);
}
test "actual EINTR is retried by poll and epoll" {
    const action: l.Sigaction = .{ .handler = .{ .handler = handler }, .mask = std.mem.zeroes(l.sigset_t), .flags = 0 };
    var old: l.Sigaction = undefined;
    _ = try m.check(l.sigaction(.USR1, &action, &old));
    defer _ = l.sigaction(.USR1, &old, null);
    var w = try W.init(t.allocator, 1, 1);
    defer w.deinit();
    var p = try Poll.init(t.allocator, w.pairs);
    defer p.deinit();
    var e = try Epoll.init(t.allocator, w.pairs);
    defer e.deinit();
    var out: [1]usize = undefined;
    for ([_]bool{ false, true }) |ep| {
        var stats: m.Stats = .{};
        const thread = try std.Thread.spawn(.{}, interrupt, .{ l.getpid(), l.gettid() });
        defer thread.join();
        const n = if (ep) try e.wait(&out, 60, &stats) else try p.wait(&out, 60, &stats);
        try t.expectEqual(@as(usize, 0), n);
        try t.expect(stats.eintr >= 1);
        try t.expect(stats.wait_calls >= 2);
    }
}
