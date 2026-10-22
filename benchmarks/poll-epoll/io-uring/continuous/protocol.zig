const std = @import("std");
pub fn body(index: u64, sequence: u64) u8 {
    return @truncate((index *% 17 +% sequence *% 31) % 251);
}
pub fn encode(out: []u8, index: u64, sequence: u64, sent_ns: u64) void {
    std.mem.writeInt(u64, out[0..8], sequence, .little);
    std.mem.writeInt(u64, out[8..16], sent_ns, .little);
    std.mem.writeInt(u64, out[16..24], index, .little);
    @memset(out[24..], body(index, sequence));
}
pub const Parser = struct {
    storage: []u8,
    used: usize = 0,
    sequence: u64 = 0,
    index: u64,
    pub fn feed(self: *Parser, input: []const u8, completed_ns: u64, latency: anytype) !u64 {
        var rest = input;
        var count: u64 = 0;
        while (rest.len > 0) {
            const n = @min(rest.len, self.storage.len - self.used);
            @memcpy(self.storage[self.used..][0..n], rest[0..n]);
            self.used += n;
            rest = rest[n..];
            if (self.used == self.storage.len) {
                const seq = std.mem.readInt(u64, self.storage[0..8], .little);
                const sent = std.mem.readInt(u64, self.storage[8..16], .little);
                const index = std.mem.readInt(u64, self.storage[16..24], .little);
                if (seq != self.sequence or index != self.index) return error.OrderOrIdentityMismatch;
                for (self.storage[24..]) |b| if (b != body(index, seq)) return error.CorruptBody;
                const completed = if (completed_ns == 0) @import("../../metrics.zig").now() else completed_ns;
                if (sent > completed) return error.InvalidTimestamp;
                try latency.append(completed - sent);
                self.sequence += 1;
                self.used = 0;
                count += 1;
            }
        }
        return count;
    }
};
test "stream parser splits and coalesces records and rejects duplicate/corruption" {
    const a = std.testing.allocator;
    var data: [128]u8 = undefined;
    encode(data[0..64], 2, 0, 10);
    encode(data[64..], 2, 1, 11);
    var storage: [64]u8 = undefined;
    var parser: Parser = .{ .storage = &storage, .index = 2 };
    var times: std.Io.Writer.Allocating = .init(a);
    defer times.deinit();
    const Sink = struct {
        n: usize = 0,
        pub fn append(s: *@This(), _: u64) !void { s.n += 1; }
    };
    var sink: Sink = .{};
    try std.testing.expectEqual(@as(u64, 0), try parser.feed(data[0..7], 20, &sink));
    try std.testing.expectEqual(@as(u64, 2), try parser.feed(data[7..], 20, &sink));
    try std.testing.expectEqual(@as(usize, 2), sink.n);
    try std.testing.expectError(error.OrderOrIdentityMismatch, parser.feed(data[0..64], 20, &sink));
    parser.used = 0;
    encode(data[0..64], 2, 2, 10);
    data[30] ^= 1;
    try std.testing.expectError(error.CorruptBody, parser.feed(data[0..64], 20, &sink));
}
