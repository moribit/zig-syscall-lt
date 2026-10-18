const std = @import("std");
const m = @import("metrics.zig");
const l = m.l;
pub const Epoll = struct {
    a: std.mem.Allocator,
    fd: l.fd_t,
    events: []l.epoll_event,
    pub fn init(a: std.mem.Allocator, pairs: []const [2]l.fd_t) !Epoll {
        const fd: l.fd_t = @intCast(try m.check(l.epoll_create1(l.EPOLL.CLOEXEC)));
        errdefer _ = l.close(fd);
        const events = try a.alloc(l.epoll_event, @max(1, pairs.len));
        errdefer a.free(events);
        for (pairs, 0..) |p, i| {
            var ev: l.epoll_event = .{ .events = l.EPOLL.IN | l.EPOLL.RDHUP, .data = .{ .u64 = i } };
            _ = try m.check(l.epoll_ctl(fd, l.EPOLL.CTL_ADD, p[0], &ev));
        }
        return .{ .a = a, .fd = fd, .events = events };
    }
    pub fn deinit(e: *Epoll) void {
        _ = l.close(e.fd);
        e.a.free(e.events);
    }
    pub fn wait(e: *Epoll, out: []usize, timeout: i32, stats: *m.Stats) !usize {
        const n = while (true) {
            stats.wait_calls += 1;
            const n = m.check(l.epoll_wait(e.fd, e.events.ptr, @intCast(e.events.len), timeout)) catch |err| switch (err) {
                error.Interrupted => {
                    stats.eintr += 1;
                    continue;
                },
                else => return err,
            };
            break n;
        };
        if (n > out.len) return error.EventCapacity;
        for (e.events[0..n], out[0..n]) |ev, *v| {
            if (ev.events & (l.EPOLL.IN | l.EPOLL.ERR | l.EPOLL.HUP | l.EPOLL.RDHUP) == 0) return error.UnexpectedEvent;
            v.* = @intCast(ev.data.u64);
        }
        return n;
    }
    pub fn remove(e: *Epoll, fd: l.fd_t) !void {
        _ = try m.check(l.epoll_ctl(e.fd, l.EPOLL.CTL_DEL, fd, null));
    }
};
