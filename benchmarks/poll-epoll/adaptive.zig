const std = @import("std");
const m = @import("metrics.zig");
const W = @import("workload.zig").Workload;
const Poll = @import("poll.zig").Poll;
const Epoll = @import("epoll.zig").Epoll;
const model = @import("model");

// Policy frozen before the dynamic evaluation: costs learned from independent
// calibration samples, EMA 1/4, 16-batch dwell, 32-batch amortization horizon,
// 10% safety margin over measured switching cost. No generator-ready input.
const Controller = struct {
    ema: f64 = 0,
    initialized: bool = false,
    dwell: usize = 0,
    switch_estimate_ns: f64,
    fn choose(c: *Controller, current_epoll: bool, observed: usize) bool {
        c.ema = if (c.initialized) c.ema * 0.75 + @as(f64, @floatFromInt(observed)) * 0.25 else @floatFromInt(observed);
        c.initialized = true;
        c.dwell += 1;
        if (c.dwell < 16) return current_epoll;
        const x = std.math.clamp((c.ema - model.ready[0]) / (model.ready[1] - model.ready[0]), 0, 1);
        const poll_ns = model.poll_ns[0] * (1 - x) + model.poll_ns[1] * x;
        const epoll_ns = model.epoll_ns[0] * (1 - x) + model.epoll_ns[1] * x;
        const saving = if (current_epoll) epoll_ns - poll_ns else poll_ns - epoll_ns;
        if (saving * 32 <= c.switch_estimate_ns * 1.1) return current_epoll;
        c.dwell = 0;
        return !current_epoll;
    }
};
const Phase = struct { ready: usize = 0, duration: u64 = 0, messages: u64 = 0, bytes: u64 = 0, batches: u64 = 0, user: u64 = 0, system: u64 = 0 };
pub fn main(init: std.process.Init) !void {
    const args = try init.minimal.args.toSlice(init.arena.allocator());
    if (args.len != 4) return error.Usage_backend_phase_ms_seed;
    const adaptive = std.mem.eql(u8, args[1], "adaptive");
    const fixed_epoll = std.mem.eql(u8, args[1], "epoll");
    if (!adaptive and !fixed_epoll and !std.mem.eql(u8, args[1], "poll")) return error.BadBackend;
    const phase_ns = (try std.fmt.parseInt(u64, args[2], 10)) * 1_000_000;
    if (phase_ns < 10_000_000) return error.PhaseTooShort;
    const seed = try std.fmt.parseInt(u64, args[3], 10);
    const n = model.fds;
    const payload = model.payload;
    var w = try W.init(init.gpa, n, seed);
    defer w.deinit();
    const setup_start = m.now();
    var poll = try Poll.init(init.gpa, w.pairs);
    defer poll.deinit();
    var epoll: Epoll = undefined;
    var active_epoll = adaptive or fixed_epoll;
    if (active_epoll) epoll = try Epoll.init(init.gpa, w.pairs);
    defer {
        if (active_epoll) epoll.deinit();
    }
    const setup_ns = m.now() - setup_start;
    var controller: Controller = .{ .switch_estimate_ns = @floatFromInt(@max(setup_ns, 1)) };
    const indices = try init.gpa.alloc(usize, n);
    defer init.gpa.free(indices);
    const received = try init.gpa.alloc(usize, n);
    defer init.gpa.free(received);
    var stats: m.Stats = .{};
    var switches: u64 = 0;
    var switch_ns: u64 = 0;
    var phases: [3]Phase = @splat(.{});
    for (&phases, [_]usize{ 41, 4096, 41 }, 0..) |*phase, ready, phase_index| {
        phase.ready = ready;
        const cpu0 = m.Cpu.get();
        const start = m.now();
        while (m.now() - start < phase_ns) {
            @memset(received, 0);
            const round = phase_index * 1_000_000 + phase.batches;
            const sent = try w.fill(ready, payload, @intCast(round), &stats);
            var bytes: usize = 0;
            var completed: usize = 0;
            const deadline = m.now() + 5_000_000_000;
            while (bytes < sent) {
                if (m.now() > deadline) return error.ConsumerTimeout;
                const count = if (active_epoll) try epoll.wait(indices, 0, &stats) else try poll.wait(indices, 0, &stats);
                for (indices[0..count]) |index| {
                    if (received[index] >= payload) return error.DuplicateEvent;
                    const got = try w.receive(index, payload - received[index], @intCast(round % 251), &stats);
                    bytes += got;
                    received[index] += got;
                    if (received[index] == payload) completed += 1;
                }
            }
            if (bytes != sent or completed != ready) return error.DataMismatch;
            for (w.order[0..ready]) |index| if (received[index] != payload) return error.MissingData;
            phase.messages += completed;
            phase.bytes += bytes;
            phase.batches += 1;
            if (adaptive) {
                const next = controller.choose(active_epoll, completed);
                if (next != active_epoll) {
                    const switch_start = m.now();
                    // Switch only after the current batch has been fully drained.
                    // Poll mode has no live epoll registrations: it must not pay
                    // epoll's producer-side ready-list maintenance implicitly.
                    if (next) epoll = try Epoll.init(init.gpa, w.pairs) else epoll.deinit();
                    const cost = m.now() - switch_start;
                    active_epoll = next;
                    switches += 1;
                    switch_ns += cost;
                    controller.switch_estimate_ns = @floatFromInt(cost);
                }
            }
        }
        phase.duration = m.now() - start;
        const cpu1 = m.Cpu.get();
        phase.user = cpu1.user - cpu0.user;
        phase.system = cpu1.system - cpu0.system;
    }
    var duration: u64 = 0;
    var messages: u64 = 0;
    for (phases) |p| {
        duration += p.duration;
        messages += p.messages;
    }
    var buf: [4096]u8 = undefined;
    var writer: std.Io.Writer = .fixed(&buf);
    try writer.print("{{\"backend\":\"{s}\",\"duration_ns\":{d},\"messages\":{d},\"setup_ns\":{d},\"switches\":{d},\"switch_ns\":{d},\"wait_calls\":{d},\"send_calls\":{d},\"recv_calls\":{d},\"errors\":0,\"phases\":[", .{ args[1], duration, messages, setup_ns, switches, switch_ns, stats.wait_calls, stats.send_calls, stats.recv_calls });
    for (phases, 0..) |p, i| {
        if (i != 0) try writer.writeByte(',');
        try writer.print("{{\"ready_fds\":{d},\"duration_ns\":{d},\"messages\":{d},\"bytes\":{d},\"batches\":{d},\"user_us\":{d},\"system_us\":{d}}}", .{ p.ready, p.duration, p.messages, p.bytes, p.batches, p.user, p.system });
    }
    try writer.writeAll("]}\n");
    try std.Io.File.stdout().writeStreamingAll(init.io, writer.buffered());
}

test "controller dwell prevents switching every sample" {
    var c: Controller = .{ .switch_estimate_ns = 0 };
    var current = true;
    for (0..15) |_| {
        const next = c.choose(current, 4096);
        try std.testing.expectEqual(current, next);
        current = next;
    }
}
