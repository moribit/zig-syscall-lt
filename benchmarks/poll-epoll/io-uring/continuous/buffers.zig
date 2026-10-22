const std = @import("std");
const l = std.os.linux;
// Keep the standard library's audited get/put/recv methods, but request the
// ordinary (non-incremental) provided-buffer contract explicitly.
pub fn init(ring: *l.IoUring, a: std.mem.Allocator, size: u32, count: u16) !l.IoUring.BufferGroup {
    const bytes = try a.alloc(u8, @as(usize, size) * count);
    errdefer a.free(bytes);
    const heads = try a.alloc(u32, count);
    errdefer a.free(heads);
    @memset(heads, 0);
    const br = try l.IoUring.setup_buf_ring(ring.fd, count, 1, .{ .inc = false });
    l.IoUring.buf_ring_init(br);
    for (0..count) |i| l.IoUring.buf_ring_add(br, bytes[i * size ..][0..size], @intCast(i), l.IoUring.buf_ring_mask(count), @intCast(i));
    l.IoUring.buf_ring_advance(br, count);
    return .{ .ring = ring, .br = br, .buffers = bytes, .buffer_size = size, .buffers_count = count, .heads = heads, .group_id = 1 };
}
