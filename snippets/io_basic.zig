const std = @import("std");

pub fn app(io: std.Io) !void {
    try std.Io.File.stdout().writeStreamingAll(io, "hello\n");
}

pub fn main(init: std.process.Init) !void {
    try app(init.io);
}
