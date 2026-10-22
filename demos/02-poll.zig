const std = @import("std");
const linux = std.os.linux;

pub fn main() !void {
    var a: [2]linux.fd_t = undefined;
    var b: [2]linux.fd_t = undefined;
    if (linux.errno(linux.pipe2(&a, .{ .NONBLOCK = true, .CLOEXEC = true })) != .SUCCESS) return error.PipeFailed;
    defer {
        _ = linux.close(a[0]);
        _ = linux.close(a[1]);
    }
    if (linux.errno(linux.pipe2(&b, .{ .NONBLOCK = true, .CLOEXEC = true })) != .SUCCESS) return error.PipeFailed;
    defer {
        _ = linux.close(b[0]);
        _ = linux.close(b[1]);
    }
    var fds = [_]linux.pollfd{
        .{ .fd = a[0], .events = linux.POLL.IN, .revents = 0 },
        .{ .fd = b[0], .events = linux.POLL.IN, .revents = 0 },
    };
    if (linux.poll(&fds, fds.len, 0) != 0) return error.ExpectedEmptyPipes;
    var buffer: [5]u8 = undefined;
    if (linux.errno(linux.read(b[0], &buffer, buffer.len)) != .AGAIN) return error.ExpectedEagain;
    std.debug.print("[read] empty non-blocking pipe: EAGAIN\n", .{});
    std.debug.print("[poll] no fd ready; waiting for fd {d}, {d}...\n", .{ a[0], b[0] });
    const thread = try std.Thread.spawn(.{}, sendLater, .{ b[0], b[1] });
    defer thread.join();
    const count = linux.poll(&fds, fds.len, 3000); // The array is passed on every call.
    if (linux.errno(count) != .SUCCESS) return error.PollFailed;
    if (count != 1 or fds[0].revents != 0 or fds[1].revents != linux.POLL.IN) return error.UnexpectedReadiness;
    std.debug.print("[poll] ready: fd {d} (data has not been read)\n", .{fds[1].fd});
    const n = linux.read(fds[1].fd, &buffer, buffer.len);
    if (linux.errno(n) != .SUCCESS) return error.ReadFailed;
    if (n != 5 or !std.mem.eql(u8, &buffer, "hello")) return error.UnexpectedData;
    std.debug.print("[read] returned={d}, buffer={s}\n", .{ n, buffer });
}

fn sendLater(read_fd: linux.fd_t, write_fd: linux.fd_t) void {
    const delay: linux.timespec = .{ .sec = 1, .nsec = 0 };
    if (linux.errno(linux.nanosleep(&delay, null)) != .SUCCESS) @panic("writer sleep failed");
    std.debug.print("[writer] pipe B: read fd={d}, write fd={d}\n", .{ read_fd, write_fd });
    if (linux.write(write_fd, "hello", 5) != 5) @panic("writer failed");
}
