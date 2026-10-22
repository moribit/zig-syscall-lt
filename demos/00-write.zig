const std = @import("std");
const linux = std.os.linux;

pub fn main() !void {
    // fd 1 is stdout. This is a raw Linux syscall, without libc.
    const n = linux.write(1, "hello\n", 6);
    if (linux.errno(n) != .SUCCESS) {
        std.debug.print("[write] errno={s}\n", .{@tagName(linux.errno(n))});
        return error.WriteFailed;
    }
    if (n != 6) return error.ShortWrite;
    std.debug.print("[write] fd=1, requested=6, returned={d}\n", .{n});
}
