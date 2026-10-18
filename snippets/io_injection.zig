const std = @import("std");
const app = @import("io_basic.zig").app;

pub fn main(init: std.process.Init) !void {
    // The normal process Init supplies Threaded in Zig 0.17.0.
    try app(init.io);
    std.debug.print("Threaded: success\n", .{});
    app(std.Io.failing) catch |err| {
        std.debug.print("failing: {s}\n", .{@errorName(err)});
        return;
    };
    return error.ExpectedIoFailure;
}
