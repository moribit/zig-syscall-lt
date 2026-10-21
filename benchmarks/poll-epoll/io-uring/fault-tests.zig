// Additional post-measurement correctness checks; no performance source changes.
const std = @import("std");
const t = std.testing;
const m = @import("../metrics.zig");
const l = m.l;
const Ring = @import("ring.zig").Ring;
const Receiver = @import("recv.zig").Receiver;
const Workload = @import("../workload.zig").Workload;
fn fdCount() usize {
    var count: usize = 0;
    for (0..128) |i| {
        if (l.errno(l.fcntl(@intCast(i), l.F.GETFD, 0)) == .SUCCESS) count += 1;
    }
    return count;
}
test "buffer and pending allocation failures close initialized ring mappings and fds" {
    var w = try Workload.init(t.allocator, 8, 19);
    defer w.deinit();
    const before = fdCount();
    for (0..2) |i| {
        var failing = std.testing.FailingAllocator.init(t.allocator, .{ .fail_index = i });
        try t.expectError(error.OutOfMemory, Receiver.init(failing.allocator(), w.pairs, 64, 8, 8, false));
        try t.expectEqual(before, fdCount());
    }
}
test "reverse arrivals identify each socket by user_data and poll signals EOF readability" {
    var w = try Workload.init(t.allocator, 8, 19);
    defer w.deinit();
    var r = try Ring.init(8, 16);
    defer r.deinit();
    var buffers: [8][8]u8 = undefined;
    for (w.pairs, 0..) |p, i| {
        _ = try r.u.recv(i, p[0], .{ .buffer = &buffers[i] }, 0);
    }
    try r.flush();
    for (0..8) |j| {
        const i = 7 - j;
        const byte = [1]u8{@intCast(i)};
        _ = try m.check(l.sendto(w.pairs[i][1], &byte, 1, 0, null, 0));
    }
    var seen: [8]bool = @splat(false);
    var total: usize = 0;
    var cq: [8]l.io_uring_cqe = undefined;
    while (total < 8) {
        const n = try r.copy(&cq, true);
        for (cq[0..n]) |c| {
            const i: usize = @intCast(c.user_data);
            try t.expect(i < 8 and !seen[i]);
            seen[i] = true;
            try t.expectEqual(@as(i32, 1), c.res);
            try t.expectEqual(@as(u8, @intCast(i)), buffers[i][0]);
            total += 1;
        }
    }
    _ = try r.u.poll_add(99, w.pairs[0][0], l.POLL.IN);
    try r.flush();
    _ = try m.check(l.shutdown(w.pairs[0][1], l.SHUT.WR));
    var count: usize = 0;
    while (count == 0) count = try r.copy(&cq, true);
    try t.expectEqual(@as(usize, 1), count);
    try t.expect(cq[0].res > 0);
    try t.expect(@as(u32, @intCast(cq[0].res)) & l.POLL.IN != 0);
    try t.expectEqual(@as(usize, 0), try m.check(l.recvfrom(w.pairs[0][0], &buffers[0], 8, 0, null, null)));
}
