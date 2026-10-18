const std = @import("std");

pub fn main() !void {
    const n = std.os.linux.write(1, "hello\n", 6);
    if (std.os.linux.errno(n) != .SUCCESS) return error.WriteFailed;
    if (n != 6) return error.ShortWrite;
}
