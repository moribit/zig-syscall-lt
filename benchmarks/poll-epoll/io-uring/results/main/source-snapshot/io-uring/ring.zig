const std = @import("std");
pub const l = std.os.linux;
const m = @import("../metrics.zig");
// The audited Zig 0.17.0 SQ/CQ implementation owns the ABI atomics and mappings.
// No SQPOLL, fixed files, multishot, or registered buffers in this baseline.
pub const Ring = struct {
    u: l.IoUring,
    setup_ns: u64,
    mmap_ns: u64,
    enters: u64 = 0,
    submitted: u64 = 0,
    copies: u64 = 0,
    interrupts: u64 = 0,
    pub fn init(entries: u16, cq_entries: u32) !Ring {
        var p = std.mem.zeroes(l.io_uring_params);
        p.flags = l.IORING_SETUP_CQSIZE;
        p.cq_entries = cq_entries;
        const start = m.now();
        const raw = l.io_uring_setup(entries, &p);
        if (l.errno(raw) != .SUCCESS) {
            std.debug.print("io_uring_setup errno={d} ({s})\n", .{ @backingInt(l.errno(raw)), @tagName(l.errno(raw)) });
            return error.SetupFailed;
        }
        const setup = m.now() - start;
        const fd: l.fd_t = @intCast(raw);
        errdefer _ = l.close(fd);
        if (p.features & l.IORING_FEAT_SINGLE_MMAP == 0) return error.SingleMmapRequired;
        const map_start = m.now();
        var sq = try l.IoUring.SubmissionQueue.init(fd, p);
        errdefer sq.deinit();
        const cq = try l.IoUring.CompletionQueue.init(fd, p, sq);
        return .{ .u = .{ .fd = fd, .sq = sq, .cq = cq, .flags = p.flags, .features = p.features }, .setup_ns = setup, .mmap_ns = m.now() - map_start };
    }
    pub fn healthy(r: *Ring) !void {
        if (@atomicLoad(u32, r.u.sq.dropped, .acquire) != 0) return error.SqDropped;
        if (@atomicLoad(u32, r.u.cq.overflow, .acquire) != 0 or @atomicLoad(u32, r.u.sq.flags, .acquire) & l.IORING_SQ_CQ_OVERFLOW != 0) return error.CqOverflow;
    }
    pub fn enter(r: *Ring, count: u32, wait: u32) !u32 {
        while (true) {
            r.enters += 1;
            const raw = l.io_uring_enter(r.u.fd, count, wait, if (wait > 0) l.IORING_ENTER_GETEVENTS else 0, null);
            switch (l.errno(raw)) {
                .SUCCESS => return @intCast(raw),
                .INTR => {
                    r.interrupts += 1;
                    continue;
                },
                else => {
                    std.debug.print("io_uring_enter errno={s}\n", .{@tagName(l.errno(raw))});
                    return error.EnterFailed;
                },
            }
        }
    }
    pub fn flush(r: *Ring) !void {
        try r.healthy();
        var count = r.u.flush_sq();
        while (count > 0) {
            const n = try r.enter(count, 0);
            if (n == 0) return error.NoSubmissionProgress;
            r.submitted += n;
            count = r.u.sq_ready();
        }
    }
    pub fn copy(r: *Ring, out: []l.io_uring_cqe, wait: bool) !usize {
        try r.healthy();
        r.copies += 1;
        if (r.u.cq_ready() == 0 and wait) _ = try r.enter(0, 1);
        try r.healthy();
        return try r.u.copy_cqes(out, 0);
    }
    pub fn deinit(r: *Ring) void {
        r.u.deinit();
    }
};
