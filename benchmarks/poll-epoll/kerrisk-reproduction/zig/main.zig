// SPDX-License-Identifier: MIT
// Independent reconstruction, not Kerrisk's original altio_speed.c.
const std = @import("std");
const l = std.os.linux;
fn check(rc: usize) !usize {
    return switch (l.errno(rc)) {
        .SUCCESS => rc,
        .INTR => error.Interrupted,
        else => error.SyscallFailed,
    };
}
fn now() u64 {
    var t: l.timespec = undefined;
    _ = check(l.clock_gettime(.MONOTONIC, &t)) catch @panic("clock");
    return @as(u64, @intCast(t.sec)) * 1_000_000_000 + @as(u64, @intCast(t.nsec));
}
fn random64(s: *u64) u64 {
    s.* ^= s.* << 13;
    s.* ^= s.* >> 7;
    s.* ^= s.* << 17;
    return s.*;
}
const Set = [1024 / @bitSizeOf(usize)]usize;
fn isset(set: *const Set, fd: l.fd_t) bool {
    const i: usize = @intCast(fd);
    return set[i / @bitSizeOf(usize)] & (@as(usize, 1) << @intCast(i % @bitSizeOf(usize))) != 0;
}
fn cpu() l.rusage {
    var u: l.rusage = undefined;
    _ = check(l.getrusage(l.rusage.SELF, &u)) catch @panic("rusage");
    return u;
}
fn us(t: l.timeval) u64 {
    return @as(u64, @intCast(t.sec)) * 1_000_000 + @as(u64, @intCast(t.usec));
}
const Bench = struct {
    ep: bool,
    po: bool,
    pairs: [][2]l.fd_t,
    fds: []l.pollfd,
    events: []l.epoll_event,
    indices: []usize,
    master: Set,
    readyset: Set,
    maxfd: l.fd_t,
    epfd: l.fd_t = -1,
    fn wait(b: *Bench, timeout: i32) !usize {
        while (true) {
            const raw = if (b.ep) l.epoll_wait(b.epfd, b.events.ptr, @intCast(b.events.len), timeout) else if (b.po) l.poll(b.fds.ptr, b.fds.len, timeout) else blk: {
                b.readyset = b.master;
                var ts: l.timespec = .{ .sec = 0, .nsec = 0 };
                break :blk l.syscall6(.pselect6, @intCast(b.maxfd + 1), @intFromPtr(&b.readyset), 0, 0, if (timeout == 0) @intFromPtr(&ts) else 0, 0);
            };
            return check(raw) catch |e| switch (e) {
                error.Interrupted => continue,
                else => return e,
            };
        }
    }
    fn scan(b: *Bench, nr: usize) !usize {
        var count: usize = 0;
        if (b.ep) {
            for (b.events[0..nr]) |ev| {
                b.indices[count] = @intCast(ev.data.u64);
                count += 1;
            }
        } else {
            for (b.fds, 0..) |fd, j| {
                if (if (b.po) fd.revents & l.POLL.IN != 0 else isset(&b.readyset, b.pairs[j][0])) {
                    b.indices[count] = j;
                    count += 1;
                }
            }
        }
        std.mem.doNotOptimizeAway(b.indices);
        if (count != nr) return error.ScanCount;
        return count;
    }
};
pub fn main(init: std.process.Init) !void {
    const a = init.gpa;
    const args = try init.minimal.args.toSlice(init.arena.allocator());
    if (args.len != 13) return error.Usage;
    const ep = std.mem.eql(u8, args[1], "epoll");
    const po = std.mem.eql(u8, args[1], "poll");
    const se = std.mem.eql(u8, args[1], "select");
    const n = try std.fmt.parseInt(usize, args[3], 10);
    const r = try std.fmt.parseInt(usize, args[4], 10);
    const loops = try std.fmt.parseInt(u64, args[5], 10);
    const timeout = try std.fmt.parseInt(i32, args[6], 10);
    const cap = try std.fmt.parseInt(usize, args[7], 10);
    const changes = try std.fmt.parseInt(usize, args[11], 10);
    var seed = try std.fmt.parseInt(u64, args[12], 10);
    if (seed == 0) seed = 1;
    const full = std.mem.eql(u8, args[10], "full");
    const api = std.mem.eql(u8, args[10], "api");
    const scan_only = std.mem.eql(u8, args[10], "scan-only");
    const verify_only = std.mem.eql(u8, args[10], "verify-only");
    const ctl_only = std.mem.eql(u8, args[10], "ctl-only");
    if (!(ep or po or se) or n == 0 or r > n or cap == 0 or loops == 0 or (timeout != 0 and timeout != -1) or (timeout == -1 and r == 0) or changes > n or (changes > 0 and !ep)) return error.InvalidArguments;
    if (!(api or full or scan_only or verify_only or ctl_only or std.mem.eql(u8, args[10], "scan") or std.mem.eql(u8, args[10], "verify")) or (full and r == 0) or (ctl_only and !ep)) return error.BadWork;
    const pipe = std.mem.eql(u8, args[2], "pipe");
    if (!pipe and !std.mem.eql(u8, args[2], "socket")) return error.BadKind;
    const contiguous = std.mem.eql(u8, args[9], "contiguous");
    if (!contiguous and !std.mem.eql(u8, args[9], "normal")) return error.BadLayout;
    const pairs = try a.alloc([2]l.fd_t, n);
    defer a.free(pairs);
    var created: usize = 0;
    defer {
        for (pairs[0..created]) |p| {
            _ = l.close(p[0]);
            _ = l.close(p[1]);
        }
    }
    const order = try a.alloc(usize, n);
    defer a.free(order);
    const indices = try a.alloc(usize, n);
    defer a.free(indices);
    const expected = try a.alloc(bool, n);
    defer a.free(expected);
    const seen = try a.alloc(bool, n);
    defer a.free(seen);
    const fds = try a.alloc(l.pollfd, n);
    defer a.free(fds);
    const events = try a.alloc(l.epoll_event, cap);
    defer a.free(events);
    for (pairs, 0..) |*p, i| {
        _ = try check(if (pipe) l.pipe2(p, .{}) else l.socketpair(l.AF.UNIX, l.SOCK.STREAM, 0, p));
        created += 1;
        order[i] = i;
    }
    if (contiguous) {
        for (pairs) |*p| {
            for (0..2) |j| {
                const d: l.fd_t = @intCast(try check(l.fcntl(p[j], l.F.DUPFD_CLOEXEC, 2 * n + 32)));
                _ = l.close(p[j]);
                p[j] = d;
            }
        }
        for (pairs, 0..) |*p, i| {
            _ = try check(l.dup3(p[0], @intCast(3 + i), 0));
            _ = l.close(p[0]);
            p[0] = @intCast(3 + i);
        }
    }
    if (std.mem.eql(u8, args[8], "random")) {
        var i = n - 1;
        while (i > 0) : (i -= 1) {
            const j = random64(&seed) % (i + 1);
            std.mem.swap(usize, &order[i], &order[j]);
        }
    } else if (std.mem.eql(u8, args[8], "middle")) {
        if (r != 1) return error.BadPlacement;
        order[0] = n / 2;
    } else if (std.mem.eql(u8, args[8], "last")) {
        if (r != 1) return error.BadPlacement;
        order[0] = n - 1;
    } else if (!std.mem.eql(u8, args[8], "first")) return error.BadPlacement;
    @memset(expected, false);
    for (order[0..r]) |i| {
        expected[i] = true;
        const nr = while (true) {
            break check(l.write(pairs[i][1], "x", 1)) catch |e| switch (e) {
                error.Interrupted => continue,
                else => return e,
            };
        };
        if (nr != 1) return error.ShortWrite;
    }
    var b: Bench = .{ .ep = ep, .po = po, .pairs = pairs, .fds = fds, .events = events, .indices = indices, .master = @splat(0), .readyset = @splat(0), .maxfd = 0 };
    for (pairs, fds) |p, *fd| {
        fd.* = .{ .fd = p[0], .events = l.POLL.IN, .revents = 0 };
        b.maxfd = @max(b.maxfd, p[0]);
        if (se) {
            if (p[0] >= 1024) return error.FdSetSize;
            const i: usize = @intCast(p[0]);
            b.master[i / @bitSizeOf(usize)] |= @as(usize, 1) << @intCast(i % @bitSizeOf(usize));
        }
    }
    const setup0 = now();
    if (ep) {
        b.epfd = @intCast(try check(l.epoll_create1(l.EPOLL.CLOEXEC)));
        for (pairs, 0..) |p, i| {
            var ev: l.epoll_event = .{ .events = l.EPOLL.IN, .data = .{ .u64 = i } };
            _ = try check(l.epoll_ctl(b.epfd, l.EPOLL.CTL_ADD, p[0], &ev));
        }
    }
    defer {
        if (ep) _ = l.close(b.epfd);
    }
    const setup = now() - setup0;
    var found: usize = 0;
    var nr: usize = 0;
    @memset(seen, false);
    for (0..n + 1) |_| {
        nr = try b.wait(0);
        if (nr != (if (ep) @min(r, cap) else r)) return error.PrimeCount;
        const count = try b.scan(nr);
        for (indices[0..count]) |i| {
            if (i >= n or !expected[i]) return error.PrimeSet;
            if (!seen[i]) {
                seen[i] = true;
                found += 1;
            }
        }
        if (found == r) break;
    }
    if (found != r) return error.PrimeFullSet;
    var ready_hash: u64 = 1469598103934665603;
    for (expected) |v| ready_hash = (ready_hash ^ @as(u64, @intFromBool(v))) *% 1099511628211;
    var calls: u64 = 0;
    var observed: u64 = 0;
    var checksum: u64 = 0;
    var controls: u64 = 0;
    const cpu0 = cpu();
    const begin = now();
    for (0..loops) |iteration| {
        if (full) @memset(seen, false);
        var distinct: usize = 0;
        while (true) {
            if (!scan_only and !verify_only and !ctl_only) {
                nr = try b.wait(timeout);
                if (nr != (if (ep) @min(r, cap) else r)) return error.TimedCount;
                calls += 1;
                observed += nr;
            }
            if (!api and !ctl_only) {
                if (verify_only) std.mem.doNotOptimizeAway(indices);
                const count = if (verify_only) nr else try b.scan(nr);
                if (full or verify_only or std.mem.eql(u8, args[10], "verify")) {
                    if (!full) @memset(seen, false);
                    for (indices[0..count]) |i| {
                        if (i >= n or !expected[i]) return error.TimedSet;
                        if (!seen[i]) {
                            seen[i] = true;
                            distinct += 1;
                        } else if (!full) return error.Duplicate;
                    }
                }
                checksum += count;
            } else checksum += nr;
            if (!full or distinct >= r) break;
        }
        for (0..changes) |j| {
            const i = (iteration * changes + j) % n;
            var ev: l.epoll_event = .{ .events = l.EPOLL.IN, .data = .{ .u64 = i } };
            _ = try check(l.epoll_ctl(b.epfd, l.EPOLL.CTL_DEL, pairs[i][0], null));
            _ = try check(l.epoll_ctl(b.epfd, l.EPOLL.CTL_ADD, pairs[i][0], &ev));
            controls += 2;
        }
    }
    const duration = now() - begin;
    const cpu1 = cpu();
    var buf: [2048]u8 = undefined;
    const text = try std.fmt.bufPrint(&buf, "{{\"ready_hash\":{d},\"duration_ns\":{d},\"setup_epoll_ns\":{d},\"wait_calls\":{d},\"events_observed\":{d},\"checksum\":{d},\"ctl_calls\":{d},\"user_us\":{d},\"system_us\":{d},\"min_fd\":{d},\"max_fd\":{d},\"preflight_ready\":{d},\"errors\":0}}\n", .{ ready_hash, duration, setup, calls, observed, checksum, controls, us(cpu1.utime) - us(cpu0.utime), us(cpu1.stime) - us(cpu0.stime), pairs[0][0], b.maxfd, found });
    try std.Io.File.stdout().writeStreamingAll(init.io, text);
}
