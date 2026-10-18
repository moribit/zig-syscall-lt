const std = @import("std");

// Reproducer for the unmodified Zig 0.17.0 standard library on Linux.
// Expected: Io/Uring.zig reports that Io.VTable has no processReplacePath.
// No build options or project-specific modules are required.
pub fn main() !void {
    var evented: std.Io.Evented = undefined;
    try evented.init(std.heap.page_allocator, .{});
    defer evented.deinit();

    const io = evented.io();
    try std.Io.File.stdout().writeStreamingAll(io, "Hello, World!\n");
}
