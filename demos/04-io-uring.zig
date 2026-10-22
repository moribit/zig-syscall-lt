const std = @import("std");
const linux = std.os.linux;

pub fn main() !void {
    // Default SIGALRM bounds direct execution; the runner adds a second timeout.
    const limit: linux.itimerspec = .{ .it_interval = .{ .sec = 0, .nsec = 0 }, .it_value = .{ .sec = 8, .nsec = 0 } };
    if (linux.errno(linux.setitimer(0, &limit, null)) != .SUCCESS) return error.TimerFailed;
    var pipe: [2]linux.fd_t = undefined;
    if (linux.errno(linux.pipe2(&pipe, .{ .CLOEXEC = true })) != .SUCCESS) return error.PipeFailed;
    defer _ = linux.close(pipe[0]);
    defer _ = linux.close(pipe[1]);
    var ring = linux.IoUring.init(8, 0) catch |err| {
        std.debug.print("[io_uring] setup failed: {s}; check kernel / seccomp / io_uring_disabled\n", .{@errorName(err)});
        return err;
    };
    defer ring.deinit();
    std.debug.print("[io_uring] ring created\n", .{});
    var buffer: [5]u8 = undefined;
    _ = try ring.read(42, pipe[0], .{ .buffer = &buffer }, 0); // IORING_OP_READ, oneshot.
    std.debug.print("[SQE] READ fd {d}, user_data=42\n", .{pipe[0]});
    const submitted = ring.submit() catch @panic("submit failed; abort with buffer still alive");
    if (submitted != 1) @panic("expected one submitted SQE");
    std.debug.print("[submit] request submitted; waiting for completion...\n", .{});
    const thread = std.Thread.spawn(.{}, sendLater, .{pipe[1]}) catch @panic("writer spawn failed");
    defer thread.join();
    // copy_cqe also advances CQ. Do not call cqe_seen again.
    const cqe = ring.copy_cqe() catch @panic("CQ wait failed; abort with buffer still alive");
    std.debug.print("[CQE] user_data={d}, res={d}\n", .{ cqe.user_data, cqe.res });
    if (cqe.user_data != 42) @panic("unexpected request identity");
    if (cqe.res < 0) {
        std.debug.print("[CQE] errno={d}\n", .{-cqe.res});
        return error.ReadFailed;
    }
    if (cqe.res != 5 or !std.mem.eql(u8, &buffer, "hello")) return error.UnexpectedData;
    std.debug.print("[buffer] {s}\n", .{buffer});
}

fn sendLater(fd: linux.fd_t) void {
    const delay: linux.timespec = .{ .sec = 1, .nsec = 0 };
    if (linux.errno(linux.nanosleep(&delay, null)) != .SUCCESS) @panic("writer sleep failed");
    std.debug.print("[writer] writing hello to fd {d}\n", .{fd});
    if (linux.write(fd, "hello", 5) != 5) @panic("writer failed");
}
