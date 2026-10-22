const std = @import("std");
const l = std.os.linux;
const Ring = @import("ring.zig").Ring;
const m = @import("../metrics.zig");
pub fn main(init: std.process.Init) !void {
    var ring = try Ring.init(8, 16);
    defer ring.deinit();
    var probe = std.mem.zeroes(l.io_uring_probe);
    const reg = l.io_uring_register(ring.u.fd, .REGISTER_PROBE, &probe, 256);
    var pair: [2]l.fd_t = undefined;
    _ = try m.check(l.socketpair(l.AF.UNIX, l.SOCK.STREAM | l.SOCK.NONBLOCK, 0, &pair));
    defer {
        _ = l.close(pair[0]);
        _ = l.close(pair[1]);
    }
    var buf: [64]u8 = undefined;
    _ = try ring.u.recv(42, pair[0], .{ .buffer = &buf }, 0);
    try ring.flush();
    const text = "io_uring verified";
    if (try m.check(l.sendto(pair[1], text.ptr, text.len, l.MSG.NOSIGNAL, null, 0)) != text.len) return error.ShortSend;
    var cq: [8]l.io_uring_cqe = undefined;
    var n: usize = 0;
    while (n == 0) n = try ring.copy(&cq, true);
    if (n != 1 or cq[0].res != text.len or cq[0].user_data != 42 or !std.mem.eql(u8, buf[0..text.len], text)) return error.InvalidRecv;
    var output: [8192]u8 = undefined;
    const result = try std.fmt.bufPrint(&output, "{{\"status\":\"SUPPORTED\",\"libc_linked\":{},\"setup_errno\":0,\"register_errno\":{d},\"features\":{d},\"sq_entries\":{d},\"cq_entries\":{d},\"recv_supported\":{},\"poll_add_supported\":{},\"cancel_supported\":{},\"bytes\":{d},\"content_valid\":true,\"enter_calls\":{d}}}\n", .{ @import("builtin").link_libc, @backingInt(l.errno(reg)), ring.u.features, ring.u.sq.sqes.len, ring.u.cq.cqes.len, probe.is_supported(.RECV), probe.is_supported(.POLL_ADD), probe.is_supported(.ASYNC_CANCEL), text.len, ring.enters });
    try std.Io.File.stdout().writeStreamingAll(init.io, result);
}
