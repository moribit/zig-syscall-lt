const std = @import("std");
const linux = std.os.linux;

pub fn main() !void {
    var pipe: [2]linux.fd_t = undefined;
    if (linux.errno(linux.pipe2(&pipe, .{})) != .SUCCESS) return error.PipeFailed;
    defer _ = linux.close(pipe[0]);
    defer _ = linux.close(pipe[1]);
    // Safety limit for direct `zig run` too: default SIGALRM ends the process.
    const limit: linux.itimerspec = .{ .it_interval = .{ .sec = 0, .nsec = 0 }, .it_value = .{ .sec = 8, .nsec = 0 } };
    if (linux.errno(linux.setitimer(0, &limit, null)) != .SUCCESS) return error.TimerFailed;
    std.debug.print("[pipe] read fd={d}, write fd={d}\n", .{ pipe[0], pipe[1] });
    const thread = try std.Thread.spawn(.{}, sendLater, .{pipe[1]});
    defer thread.join();
    var buffer: [5]u8 = undefined;
    std.debug.print("[read] waiting for data...\n", .{});
    const n = linux.read(pipe[0], &buffer, buffer.len);
    if (linux.errno(n) != .SUCCESS) return error.ReadFailed;
    if (n != 5 or !std.mem.eql(u8, &buffer, "hello")) return error.UnexpectedData;
    std.debug.print("[read] returned={d}, buffer={s}\n", .{ n, buffer });
}

fn sendLater(fd: linux.fd_t) void {
    const delay: linux.timespec = .{ .sec = 1, .nsec = 0 };
    if (linux.errno(linux.nanosleep(&delay, null)) != .SUCCESS) @panic("writer sleep failed");
    std.debug.print("[writer] writing hello to fd {d}\n", .{fd});
    if (linux.write(fd, "hello", 5) != 5) @panic("writer failed");
}
