const std = @import("std");

fn value() usize {
    return 42;
}

fn countedValue(calls: *usize) usize {
    calls.* += 1;
    return 42;
}

fn failedValue() error{ExampleFailure}!usize {
    return error.ExampleFailure;
}

test "async permits immediate execution without concurrency support" {
    const io = std.Io.failing;
    var calls: usize = 0;
    var future = io.async(countedValue, .{&calls});
    try std.testing.expectEqual(1, calls);
    try std.testing.expectEqual(42, future.await(io));
    // await and cancel remain valid after the result is available.
    try std.testing.expectEqual(42, future.await(io));
    try std.testing.expectEqual(42, future.cancel(io));
}

test "concurrent reports an implementation without concurrency support" {
    const io = std.Io.failing;
    try std.testing.expectError(error.ConcurrencyUnavailable, io.concurrent(value, .{}));
}

test "Future preserves the callee error union" {
    const io = std.Io.failing;
    var future = io.async(failedValue, .{});
    defer _ = future.cancel(io) catch {};
    try std.testing.expectError(error.ExampleFailure, future.await(io));
}
