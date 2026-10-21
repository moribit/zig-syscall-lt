const std = @import("std");
const m = @import("metrics.zig");
const l = m.l;
pub const Workload = struct {
    allocator: std.mem.Allocator,
    pairs: [][2]l.fd_t,
    order: []usize,
    pub fn init(a: std.mem.Allocator, n: usize, seed: u64) !Workload {
        const pairs = try a.alloc([2]l.fd_t, n);
        errdefer a.free(pairs);
        var made: usize = 0;
        errdefer for (pairs[0..made]) |p| {
            _ = l.close(p[0]);
            _ = l.close(p[1]);
        };
        for (pairs) |*p| {
            _ = try m.check(l.socketpair(l.AF.UNIX, l.SOCK.STREAM | l.SOCK.NONBLOCK | l.SOCK.CLOEXEC, 0, p));
            made += 1;
        }
        const order = try a.alloc(usize, n);
        for (order, 0..) |*v, i| v.* = i;
        var rng = std.Random.DefaultPrng.init(seed);
        rng.random().shuffle(usize, order);
        return .{ .allocator = a, .pairs = pairs, .order = order };
    }
    pub fn deinit(w: *Workload) void {
        for (w.pairs) |p| {
            _ = l.close(p[0]);
            _ = l.close(p[1]);
        }
        w.allocator.free(w.pairs);
        w.allocator.free(w.order);
    }
    pub fn fill(w: *Workload, ready: usize, payload: usize, round: usize, stats: *m.Stats) !u64 {
        var buf: [1024]u8 = undefined;
        const byte: u8 = @intCast(round % 251);
        @memset(buf[0..payload], byte);
        const deadline = m.now() + 5_000_000_000;
        for (w.order[0..ready]) |i| {
            var offset: usize = 0;
            while (offset < payload) {
                stats.send_calls += 1;
                const n = m.check(l.sendto(w.pairs[i][1], buf[offset..payload].ptr, payload - offset, l.MSG.NOSIGNAL, null, 0)) catch |err| switch (err) {
                    error.Interrupted => {
                        stats.eintr += 1;
                        continue;
                    },
                    error.WouldBlock => {
                        stats.eagain += 1;
                        if (m.now() > deadline) return error.ProducerTimeout;
                        continue;
                    },
                    else => return err,
                };
                if (n == 0) return error.ZeroWrite;
                offset += n;
            }
        }
        return @intCast(ready * payload);
    }
    // A fixed per-fd budget, identical for both backends. Return fewer bytes on
    // EAGAIN and let LT readiness notify again; EOF before target is an error.
    pub fn receive(w: *Workload, index: usize, remaining: usize, byte: u8, stats: *m.Stats) !usize {
        var buf: [1024]u8 = undefined;
        var total: usize = 0;
        const budget = @min(remaining, buf.len);
        while (total < budget) {
            stats.recv_calls += 1;
            const n = m.check(l.recvfrom(w.pairs[index][0], buf[0 .. budget - total].ptr, budget - total, 0, null, null)) catch |err| switch (err) {
                error.Interrupted => {
                    stats.eintr += 1;
                    continue;
                },
                error.WouldBlock => {
                    stats.eagain += 1;
                    break;
                },
                else => return err,
            };
            if (n == 0) return error.UnexpectedEof;
            for (buf[0..n]) |v| if (v != byte) return error.CorruptData;
            total += n;
        }
        return total;
    }
};
