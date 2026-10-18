const std = @import("std");
const options = @import("backend_options");

fn app(io: std.Io) !void {
    try std.Io.File.stdout().writeStreamingAll(
        io,
        "Hello, World!\n",
    );
}

// Selected at build time so an experimental backend's compile error does not
// prevent the Threaded example from running. app() is identical in both builds.
pub fn main(init: std.process.Init) !void {
    if (options.evented) {
        var backend: std.Io.Evented = undefined;
        try backend.init(init.gpa, .{});
        defer backend.deinit();
        try app(backend.io());
    } else {
        var backend = std.Io.Threaded.init(init.gpa, .{});
        defer backend.deinit();
        try app(backend.io());
    }
}
