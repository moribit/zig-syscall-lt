const std = @import("std");
const linux = std.os.linux;

// Optional appendix: one read from /dev/zero, no performance claim.
pub fn main() !void {
    var ring = try linux.IoUring.init(8, 0);
    defer ring.deinit();
    const opened = linux.openat(linux.AT.FDCWD, "/dev/zero", .{ .ACCMODE = .RDONLY }, 0);
    if (linux.errno(opened) != .SUCCESS) return error.OpenFailed;
    const fd: linux.fd_t = @intCast(opened);
    defer _ = linux.close(fd);
    var buf: [128]u8 = undefined;
    _ = try ring.read(42, fd, .{ .buffer = &buf }, 0);
    _ = try ring.submit();
    const cqe = try ring.copy_cqe(); // Also advances CQ. Do not call cqe_seen.
    if (cqe.res < 0) return error.ReadFailed;
    if (cqe.user_data != 42 or cqe.res != buf.len) return error.UnexpectedCompletion;
    for (buf) |byte| if (byte != 0) return error.UnexpectedData;
    std.debug.print("user_data={d}, res={d}\n", .{ cqe.user_data, cqe.res });
}
