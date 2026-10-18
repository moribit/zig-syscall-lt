// Diagnostic workloads, not additive partitions of the original measurement.
const std = @import("std");
const m = @import("metrics.zig");
const l = m.l;
const W = @import("workload.zig").Workload;
const Poll = @import("poll.zig").Poll;
const Epoll = @import("epoll.zig").Epoll;
pub fn main(init: std.process.Init) !void {
    const args = try init.minimal.args.toSlice(init.arena.allocator());
    if (args.len != 7) return error.Usage_backend_mode_N_ready_repeats_seed;
    const ep = std.mem.eql(u8, args[1], "epoll");
    const n = try std.fmt.parseInt(usize, args[3], 10);
    const ready = try std.fmt.parseInt(usize, args[4], 10);
    const repeats = try std.fmt.parseInt(usize, args[5], 10);
    const seed = try std.fmt.parseInt(u64, args[6], 10);
    var w = try W.init(init.gpa, n, seed);
    defer w.deinit();
    var p = try Poll.init(init.gpa, w.pairs);
    defer p.deinit();
    var e: Epoll = undefined;
    if (ep) e = try Epoll.init(init.gpa, w.pairs);
    defer {
        if (ep) e.deinit();
    }
    var stats: m.Stats = .{};
    _ = try w.fill(ready, 64, 0, &stats);
    const out = try init.gpa.alloc(usize, n);
    defer init.gpa.free(out);
    const seen = try init.gpa.alloc(bool, n);
    defer init.gpa.free(seen);
    const expected = try init.gpa.alloc(bool, n);
    defer init.gpa.free(expected);
    @memset(expected, false);
    for (w.order[0..ready]) |i| expected[i] = true;
    if ((if (ep) try e.wait(out, 0, &stats) else try p.wait(out, 0, &stats)) != ready) return error.WrongCount;
    var checksum: usize = 0;
    const cpu0 = m.Cpu.get();
    const start = m.now();
    for (0..repeats) |_| {
        if (std.mem.eql(u8, args[2], "combined")) {
            checksum += if (ep) try e.wait(out, 0, &stats) else try p.wait(out, 0, &stats);
        } else if (std.mem.eql(u8, args[2], "syscall")) {
            const count = try m.check(if (ep) l.epoll_wait(e.fd, e.events.ptr, @intCast(n), 0) else l.poll(p.fds.ptr, n, 0));
            checksum += count;
        } else if (std.mem.eql(u8, args[2], "scan")) {
            // Compiler barriers keep the prepared result arrays and output observable.
            std.mem.doNotOptimizeAway(if (ep) @intFromPtr(e.events.ptr) else @intFromPtr(p.fds.ptr));
            var count: usize = 0;
            if (ep) {
                for (e.events[0..ready]) |ev| {
                    out[count] = @intCast(ev.data.u64);
                    count += 1;
                }
            } else {
                for (p.fds, 0..) |fd, i| {
                    if (fd.revents & (l.POLL.IN | l.POLL.ERR | l.POLL.HUP) != 0) {
                        out[count] = i;
                        count += 1;
                    }
                }
            }
            std.mem.doNotOptimizeAway(out);
            checksum += count;
        } else if (std.mem.eql(u8, args[2], "validate")) {
            std.mem.doNotOptimizeAway(out);
            @memset(seen, false);
            for (out[0..ready]) |i| {
                if (!expected[i] or seen[i]) return error.WrongSet;
                seen[i] = true;
            }
            checksum += ready;
        } else if (std.mem.eql(u8, args[2], "clocks")) {
            const t = m.now();
            std.mem.doNotOptimizeAway(m.now() - t);
            checksum += ready;
        } else return error.BadMode;
    }
    const elapsed = m.now() - start;
    const cpu1 = m.Cpu.get();
    if (checksum != ready * repeats) return error.WrongChecksum;
    var buf: [1024]u8 = undefined;
    const text = try std.fmt.bufPrint(&buf, "{{\"backend\":\"{s}\",\"mode\":\"{s}\",\"fds\":{d},\"ready_fds\":{d},\"iterations\":{d},\"duration_ns\":{d},\"user_us\":{d},\"system_us\":{d},\"checksum\":{d}}}\n", .{ args[1], args[2], n, ready, repeats, elapsed, cpu1.user - cpu0.user, cpu1.system - cpu0.system, checksum });
    try std.Io.File.stdout().writeStreamingAll(init.io, text);
}
