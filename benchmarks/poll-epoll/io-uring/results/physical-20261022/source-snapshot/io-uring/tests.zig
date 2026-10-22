const std = @import("std");
const t = std.testing;
const Ring = @import("ring.zig").Ring;
const Receiver = @import("recv.zig").Receiver;
const l = @import("ring.zig").l;
const m = @import("../metrics.zig");
const Workload = @import("../workload.zig").Workload;
fn pair() ![2]l.fd_t {
    var p: [2]l.fd_t = undefined;
    _ = try m.check(l.socketpair(l.AF.UNIX, l.SOCK.STREAM | l.SOCK.NONBLOCK, 0, &p));
    return p;
}
fn close(p: [2]l.fd_t) void {
    _ = l.close(p[0]);
    _ = l.close(p[1]);
}
fn take(r: *Ring) !l.io_uring_cqe {
    var c: [1]l.io_uring_cqe = undefined;
    while (try r.copy(&c, true) == 0) {}
    return c[0];
}
test "RECV before arrival, partial completion, repeated receive and EAGAIN" {
    var r = try Ring.init(4, 8);
    defer r.deinit();
    const p = try pair();
    defer close(p);
    var buf: [16]u8 = undefined;
    _ = try r.u.recv(1, p[0], .{ .buffer = &buf }, 0);
    try r.flush();
    try t.expectEqual(@as(u32, 0), r.u.cq_ready());
    _ = try m.check(l.sendto(p[1], "abc", 3, 0, null, 0));
    const c = try take(&r);
    try t.expectEqual(@as(i32, 3), c.res);
    try t.expectEqualStrings("abc", buf[0..3]);
    _ = try r.u.recv(2, p[0], .{ .buffer = buf[3..] }, 0);
    try r.flush();
    _ = try m.check(l.sendto(p[1], "defgh", 5, 0, null, 0));
    try t.expectEqual(@as(i32, 5), (try take(&r)).res);
    try t.expectEqualStrings("abcdefgh", buf[0..8]);
    _ = try r.u.recv(3, p[0], .{ .buffer = &buf }, l.MSG.DONTWAIT);
    try r.flush();
    try t.expectEqual(-@as(i32, @backingInt(l.E.AGAIN)), (try take(&r)).res);
}
test "EOF and invalid fd are explicit terminal completions" {
    var r = try Ring.init(4, 8);
    defer r.deinit();
    const p = try pair();
    defer close(p);
    var buf: [8]u8 = undefined;
    _ = try r.u.recv(1, -1, .{ .buffer = &buf }, 0);
    try r.flush();
    try t.expectEqual(-@as(i32, @backingInt(l.E.BADF)), (try take(&r)).res);
    _ = try r.u.recv(2, p[0], .{ .buffer = &buf }, 0);
    try r.flush();
    _ = try m.check(l.shutdown(p[1], 1));
    try t.expectEqual(@as(i32, 0), (try take(&r)).res);
}
test "SQ full, wraparound, no dropped entries" {
    var r = try Ring.init(2, 4);
    defer r.deinit();
    for (0..100) |round| {
        for (0..2) |j| {
            const sqe = try r.u.get_sqe();
            sqe.prep_nop();
            sqe.user_data = round * 2 + j;
        }
        try t.expectError(error.SubmissionQueueFull, r.u.get_sqe());
        try r.flush();
        try t.expectEqual(@as(u64, round * 2), (try take(&r)).user_data);
        try t.expectEqual(@as(u64, round * 2 + 1), (try take(&r)).user_data);
        try r.healthy();
    }
}
test "real CQ overflow or backlog is detected, never silently discarded" {
    var r = try Ring.init(2, 2);
    defer r.deinit();
    for (0..2) |_| {
        for (0..2) |_| {
            const sqe = try r.u.get_sqe();
            sqe.prep_nop();
        }
        try r.flush();
    }
    try t.expectError(error.CqOverflow, r.healthy());
}
test "zero arrival and mixed pending requests cancel to terminal CQEs before buffer free" {
    for ([_]bool{ false, true }) |poll_mode| {
        var w = try Workload.init(t.allocator, 64, 19);
        defer w.deinit();
        var r = try Receiver.init(t.allocator, w.pairs, 64, 8, 8, poll_mode);
        try t.expectError(error.DuplicateReceive, r.queue(0, 0));
        try r.finish();
        for (r.pending) |v| try t.expect(!v);
        r.deinit();
    }
}
fn fdCount() usize {
    var count: usize = 0;
    for (0..128) |i| {
        if (l.errno(l.fcntl(@intCast(i), l.F.GETFD, 0)) == .SUCCESS) count += 1;
    }
    return count;
}
test "initialization failure and repeated ring lifecycle do not leak fds" {
    const before = fdCount();
    try t.expectError(error.SetupFailed, Ring.init(0, 1));
    for (0..10) |_| {
        var r = try Ring.init(8, 16);
        r.deinit();
    }
    try t.expectEqual(before, fdCount());
}

fn handler(_: l.SIG) callconv(.c) void {}
fn signalThenSend(pid: l.pid_t, tid: l.pid_t, fd: l.fd_t) void {
    const delay: l.timespec = .{ .sec = 0, .nsec = 20_000_000 };
    _ = l.nanosleep(&delay, null);
    _ = l.tgkill(pid, tid, .USR1);
    _ = l.nanosleep(&delay, null);
    _ = l.sendto(fd, "z", 1, l.MSG.NOSIGNAL, null, 0);
}
test "interrupted enter retries until the actual receive completes" {
    const action: l.Sigaction = .{ .handler = .{ .handler = handler }, .mask = std.mem.zeroes(l.sigset_t), .flags = 0 };
    var old: l.Sigaction = undefined;
    _ = try m.check(l.sigaction(.USR1, &action, &old));
    defer _ = l.sigaction(.USR1, &old, null);
    var r = try Ring.init(4, 8);
    defer r.deinit();
    const p = try pair();
    defer close(p);
    var buf: [8]u8 = undefined;
    _ = try r.u.recv(1, p[0], .{ .buffer = &buf }, 0);
    try r.flush();
    const thread = try std.Thread.spawn(.{}, signalThenSend, .{ l.getpid(), l.gettid(), p[1] });
    defer thread.join();
    try t.expectEqual(@as(i32, 1), (try take(&r)).res);
    try t.expect(r.interrupts >= 1);
}
