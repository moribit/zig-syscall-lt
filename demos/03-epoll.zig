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
    const created = linux.epoll_create1(linux.EPOLL.CLOEXEC);
    if (linux.errno(created) != .SUCCESS) return error.EpollCreateFailed;
    const epfd: linux.fd_t = @intCast(created);
    defer _ = linux.close(epfd);
    std.debug.print("[epoll] created fd={d}\n", .{epfd});
    for ([_]linux.fd_t{ a[0], b[0] }) |fd| {
        var event: linux.epoll_event = .{ .events = linux.EPOLL.IN, .data = .{ .fd = fd } }; // Level-triggered.
        if (linux.errno(linux.epoll_ctl(epfd, linux.EPOLL.CTL_ADD, fd, &event)) != .SUCCESS) return error.EpollAddFailed;
        std.debug.print("[epoll_ctl] ADD fd {d}\n", .{fd});
    }
    var events: [2]linux.epoll_event = undefined;
    if (linux.epoll_wait(epfd, &events, events.len, 0) != 0) return error.ExpectedEmptyPipes;
    std.debug.print("[epoll_wait] no fd ready; waiting...\n", .{});
    const thread = try std.Thread.spawn(.{}, sendLater, .{ b[0], b[1] });
    defer thread.join();
    const count = linux.epoll_wait(epfd, &events, events.len, 3000);
    if (linux.errno(count) != .SUCCESS) return error.EpollWaitFailed;
    if (count != 1 or events[0].data.fd != b[0] or events[0].events != linux.EPOLL.IN) return error.UnexpectedReadiness;
    std.debug.print("[epoll_wait] ready: fd {d} (data has not been read)\n", .{events[0].data.fd});
    var buffer: [5]u8 = undefined;
    const n = linux.read(events[0].data.fd, &buffer, buffer.len);
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
