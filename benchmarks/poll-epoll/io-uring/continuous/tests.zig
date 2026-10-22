const std = @import("std");
const t = std.testing;
const l = std.os.linux;
const Ring = @import("../ring.zig").Ring;
const m = @import("../../metrics.zig");
fn pair() ![2]l.fd_t {
    var p: [2]l.fd_t = undefined;
    _ = try m.check(l.socketpair(l.AF.UNIX, l.SOCK.STREAM | l.SOCK.NONBLOCK, 0, &p));
    return p;
}
fn take(r: *Ring) !l.io_uring_cqe {
    var out: [1]l.io_uring_cqe = undefined;
    while (try r.copy(&out, true) == 0) {}
    return out[0];
}
test "provided buffer multishot: multiple completions per SQE, recycle, EOF terminal" {
    var ring = try Ring.init(8, 32);
    defer ring.deinit();
    var group = try l.IoUring.BufferGroup.init(&ring.u, t.allocator, 7, 64, 8);
    defer group.deinit(t.allocator);
    const p = try pair();
    defer _ = l.close(p[0]);
    defer _ = l.close(p[1]);
    _ = try group.recv_multishot(9, p[0], 0);
    try ring.flush();
    for (0..20) |_| {
        _ = try m.check(l.sendto(p[1], "hello", 5, l.MSG.NOSIGNAL, null, 0));
        var received: usize = 0;
        while (received < 5) {
            const c = try take(&ring);
            try t.expect(c.res > 0);
            try t.expect(c.flags & l.IORING_CQE_F_MORE != 0);
            try t.expect(c.flags & l.IORING_CQE_F_BUFFER != 0);
            const bytes = try group.get(c);
            try t.expectEqualStrings("hello"[received..][0..bytes.len], bytes);
            received += bytes.len;
            try group.put(c);
        }
    }
    try t.expectEqual(@as(u64, 1), ring.submitted);
    _ = try m.check(l.shutdown(p[1], 1));
    const end = try take(&ring);
    try t.expectEqual(@as(i32, 0), end.res);
    try t.expect(end.flags & l.IORING_CQE_F_MORE == 0);
    if (end.flags & l.IORING_CQE_F_BUFFER != 0) try group.put(end);
    try ring.healthy();
}
test "provided buffer exhaustion terminates, can recycle and rearm" {
    var ring = try Ring.init(8, 32);
    defer ring.deinit();
    var group = try l.IoUring.BufferGroup.init(&ring.u, t.allocator, 1, 64, 1);
    defer group.deinit(t.allocator);
    const p = try pair();
    defer _ = l.close(p[0]);
    defer _ = l.close(p[1]);
    _ = try group.recv_multishot(1, p[0], 0);
    try ring.flush();
    var data: [128]u8 = @splat(42);
    _ = try m.check(l.sendto(p[1], &data, data.len, l.MSG.NOSIGNAL, null, 0));
    const first = try take(&ring);
    try t.expectEqual(@as(i32, 64), first.res);
    const exhausted = try take(&ring);
    try t.expectEqual(-@as(i32, @backingInt(l.E.NOBUFS)), exhausted.res);
    try t.expect(exhausted.flags & l.IORING_CQE_F_MORE == 0);
    try group.put(first);
    _ = try group.recv_multishot(2, p[0], 0);
    try ring.flush();
    const second = try take(&ring);
    try t.expectEqual(@as(i32, 64), second.res);
    try group.put(second);
    // There may already be a terminal ENOBUFS CQE; drain until the target
    // request is terminal. Never free its buffers on cancellation ACK alone.
    _ = try ring.u.cancel(99, 2, 0);
    try ring.flush();
    var terminal = second.flags & l.IORING_CQE_F_MORE == 0;
    var ack = false;
    while (!terminal or !ack) {
        const c = try take(&ring);
        if (c.user_data == 99) { ack = true; } else {
            if (c.flags & l.IORING_CQE_F_BUFFER != 0) try group.put(c);
            terminal = c.flags & l.IORING_CQE_F_MORE == 0;
        }
    }
    try ring.healthy();
}
test "cancel idle multishot retains buffers until terminal CQE" {
    var ring = try Ring.init(8, 32);
    defer ring.deinit();
    var group = try l.IoUring.BufferGroup.init(&ring.u, t.allocator, 3, 64, 8);
    defer group.deinit(t.allocator);
    const p = try pair();
    defer _ = l.close(p[0]);
    defer _ = l.close(p[1]);
    _ = try group.recv_multishot(1, p[0], 0);
    try ring.flush();
    _ = try ring.u.cancel(2, 1, 0);
    try ring.flush();
    var target = false;
    var ack = false;
    while (!target or !ack) {
        const c = try take(&ring);
        if (c.user_data == 1) {
            try t.expectEqual(-@as(i32, @backingInt(l.E.CANCELED)), c.res);
            try t.expect(c.flags & l.IORING_CQE_F_MORE == 0);
            target = true;
        } else {
            try t.expectEqual(@as(i32, 0), c.res);
            ack = true;
        }
    }
}
