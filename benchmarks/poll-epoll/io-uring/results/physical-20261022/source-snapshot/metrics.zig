const std = @import("std");
pub const l = std.os.linux;
pub const Stats = struct {
    wait_calls: u64 = 0,
    recv_calls: u64 = 0,
    send_calls: u64 = 0,
    eintr: u64 = 0,
    eagain: u64 = 0,
    errors: u64 = 0,
};
pub fn check(rc: usize) !usize {
    return switch (l.errno(rc)) {
        .SUCCESS => rc,
        .INTR => error.Interrupted,
        .AGAIN => error.WouldBlock,
        else => error.SyscallFailed,
    };
}
pub fn now() u64 {
    var ts: l.timespec = undefined;
    _ = check(l.clock_gettime(.MONOTONIC, &ts)) catch @panic("clock_gettime");
    return @as(u64, @intCast(ts.sec)) * 1_000_000_000 + @as(u64, @intCast(ts.nsec));
}
pub const Cpu = struct {
    user: u64,
    system: u64,
    pub fn get() Cpu {
        var u: l.rusage = undefined;
        _ = check(l.getrusage(l.rusage.SELF, &u)) catch @panic("getrusage");
        return .{ .user = @as(u64, @intCast(u.utime.sec)) * 1_000_000 + @as(u64, @intCast(u.utime.usec)), .system = @as(u64, @intCast(u.stime.sec)) * 1_000_000 + @as(u64, @intCast(u.stime.usec)) };
    }
};
