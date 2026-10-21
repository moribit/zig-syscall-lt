const std = @import("std");
const m = @import("metrics.zig");
const l = m.l;
pub const Poll = struct {
    a: std.mem.Allocator,
    fds: []l.pollfd,
    pub fn init(a: std.mem.Allocator, pairs: []const [2]l.fd_t) !Poll {
        const fds = try a.alloc(l.pollfd, pairs.len);
        for (fds, pairs) |*fd, p| fd.* = .{ .fd = p[0], .events = l.POLL.IN, .revents = 0 };
        return .{ .a = a, .fds = fds };
    }
    pub fn deinit(p: *Poll) void {
        p.a.free(p.fds);
    }
    pub fn wait(p: *Poll, out: []usize, timeout: i32, stats: *m.Stats) !usize {
        while (true) {
            stats.wait_calls += 1;
            _ = m.check(l.poll(p.fds.ptr, p.fds.len, timeout)) catch |err| switch (err) {
                error.Interrupted => {
                    stats.eintr += 1;
                    continue;
                },
                else => return err,
            };
            break;
        }
        var n: usize = 0;
        for (p.fds, 0..) |fd, i| {
            if (fd.revents & l.POLL.NVAL != 0) return error.InvalidFd;
            if (fd.revents & (l.POLL.IN | l.POLL.ERR | l.POLL.HUP) != 0) {
                if (n == out.len) return error.EventCapacity;
                out[n] = i;
                n += 1;
            }
        }
        return n;
    }
    pub fn remove(p: *Poll, index: usize) !void {
        p.fds[index].fd = -1;
    }
};
