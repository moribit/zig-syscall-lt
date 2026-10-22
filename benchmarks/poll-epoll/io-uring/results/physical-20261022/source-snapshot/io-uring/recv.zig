const std = @import("std");
const m = @import("../metrics.zig");
const l = m.l;
const Ring = @import("ring.zig").Ring;
pub const Receiver = struct {
    a: std.mem.Allocator,
    ring: Ring,
    pairs: []const [2]l.fd_t,
    buffers: []u8,
    pending: []bool,
    payload: usize,
    batch: usize,
    poll_mode: bool,
    initial_submit_ns: u64 = 0,
    allocation_ns: u64 = 0,
    pub fn init(a: std.mem.Allocator, pairs: []const [2]l.fd_t, payload: usize, capacity: u16, batch: usize, poll_mode: bool) !Receiver {
        const cq: u32 = @intCast(try std.math.ceilPowerOfTwo(usize, @max(pairs.len * 2, @as(usize, capacity) * 2)));
        var ring = try Ring.init(capacity, cq);
        var transferred = false;
        errdefer if (!transferred) ring.deinit();
        const start = m.now();
        const buffers = try a.alloc(u8, pairs.len * payload);
        errdefer if (!transferred) a.free(buffers);
        @memset(buffers, 0);
        const pending = try a.alloc(bool, pairs.len);
        errdefer if (!transferred) a.free(pending);
        @memset(pending, false);
        var r: Receiver = .{ .a = a, .ring = ring, .pairs = pairs, .buffers = buffers, .pending = pending, .payload = payload, .batch = batch, .poll_mode = poll_mode, .allocation_ns = m.now() - start };
        transferred = true;
        errdefer r.deinit();
        const submit_start = m.now();
        // Only fd identities, never Producer.order or future Ready membership.
        for (pairs, 0..) |_, i| try r.queue(i, 0);
        try r.ring.flush();
        r.initial_submit_ns = m.now() - submit_start;
        return r;
    }
    pub fn queue(r: *Receiver, i: usize, offset: usize) !void {
        if (r.pending[i]) return error.DuplicateReceive;
        if (r.ring.u.sq_ready() >= r.ring.u.sq.sqes.len) try r.ring.flush();
        if (r.poll_mode) {
            _ = try r.ring.u.poll_add(i, r.pairs[i][0], l.POLL.IN);
        } else {
            _ = try r.ring.u.recv(i, r.pairs[i][0], .{ .buffer = r.buffers[i * r.payload + offset .. (i + 1) * r.payload] }, 0);
        }
        r.pending[i] = true;
        if (r.ring.u.sq_ready() >= r.batch) try r.ring.flush();
    }
    // Cancel acknowledgements are NOT a substitute for target terminal CQEs.
    pub fn finish(r: *Receiver) !void {
        try r.ring.flush();
        var requests: usize = 0;
        for (r.pending, 0..) |pending, i| {
            if (!pending) continue;
            if (r.ring.u.sq_ready() >= r.ring.u.sq.sqes.len) try r.ring.flush();
            _ = try r.ring.u.cancel((@as(u64, 1) << 63) | i, i, 0);
            requests += 1;
        }
        try r.ring.flush();
        var targets: usize = requests;
        var acks: usize = requests;
        var cq: [256]l.io_uring_cqe = undefined;
        while (targets > 0 or acks > 0) {
            const n = try r.ring.copy(&cq, true);
            for (cq[0..n]) |c| {
                if (c.user_data & (@as(u64, 1) << 63) != 0) {
                    if (acks == 0 or (c.res != 0 and c.res != -@as(i32, @backingInt(l.E.NOENT)) and c.res != -@as(i32, @backingInt(l.E.ALREADY)))) return error.CancelFailed;
                    acks -= 1;
                } else {
                    const i: usize = @intCast(c.user_data);
                    if (i >= r.pending.len or !r.pending[i] or targets == 0) return error.InvalidTerminal;
                    r.pending[i] = false;
                    targets -= 1;
                    if (c.res != -@as(i32, @backingInt(l.E.CANCELED)) and c.res != 0) return error.UnexpectedTerminal;
                }
            }
        }
        try r.ring.healthy();
    }
    pub fn deinit(r: *Receiver) void {
        // Panic aborts without freeing live buffers if safe draining cannot finish.
        r.finish() catch @panic("cannot safely drain outstanding requests");
        r.ring.deinit();
        r.a.free(r.buffers);
        r.a.free(r.pending);
    }
};
