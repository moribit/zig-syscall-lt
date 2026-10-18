const std = @import("std");
const linux = std.os.linux;

// Blocking stdin-to-stdout echo. Read until EOF and handle short writes.
pub fn main() !void {
    var buf: [10]u8 = undefined;
    while (true) {
        const n = linux.read(0, &buf, buf.len);
        switch (linux.errno(n)) {
            .SUCCESS => {},
            .INTR => continue,
            else => return error.ReadFailed,
        }
        if (n == 0) return;
        var offset: usize = 0;
        while (offset < n) {
            const written = linux.write(1, buf[offset..n].ptr, n - offset);
            switch (linux.errno(written)) {
                .SUCCESS => {},
                .INTR => continue,
                else => return error.WriteFailed,
            }
            if (written == 0) return error.WriteZero;
            offset += written;
        }
    }
}
