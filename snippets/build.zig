const std = @import("std");

pub fn build(b: *std.Build) void {
    const backend = b.option(enum { threaded, evented }, "backend", "I/O backend (default: threaded)") orelse .threaded;
    const options = b.addOptions();
    options.addOption(bool, "evented", backend == .evented);
    const module = b.createModule(.{
        .root_source_file = b.path("io_backend_demo.zig"),
        .target = b.standardTargetOptions(.{}),
        .optimize = b.standardOptimizeOption(.{}),
    });
    module.addOptions("backend_options", options);
    const exe = b.addExecutable(.{ .name = "io_backend_demo", .root_module = module });
    b.installArtifact(exe);
}
