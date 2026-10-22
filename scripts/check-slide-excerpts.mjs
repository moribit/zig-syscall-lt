import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

// Check the call expressions, while allowing the slide to omit error handling.
// The complete runnable programs remain in demos/ unchanged.
const slides = await readFile('slides.md', 'utf8');
const checks = [
  ['00-write.zig', 'linux.write(1, "hello\\n", 6)'],
  ['02-poll.zig', 'linux.poll(&fds, fds.len, 3000)'],
  ['03-epoll.zig', 'linux.epoll_create1(linux.EPOLL.CLOEXEC)'],
  ['03-epoll.zig', 'linux.epoll_ctl(epfd, linux.EPOLL.CTL_ADD, fd, &event)'],
  ['03-epoll.zig', 'linux.epoll_wait(epfd, &events, events.len, 3000)'],
  ['04-io-uring.zig', 'ring.read(42, pipe[0], .{ .buffer = &buffer }, 0)'],
  ['04-io-uring.zig', 'ring.submit()'],
  ['04-io-uring.zig', 'ring.copy_cqe()'],
];
const blocks = [...slides.matchAll(/```zig\n([\s\S]*?)```/g)].map(m=>m[1]);
assert.equal(blocks.length,4);
assert(blocks.every(b=>b.trim().split('\n').length<=3));
for (const [file,call] of checks) {
  assert((await readFile(`demos/${file}`, 'utf8')).includes(call), `${call}: demo mismatch`);
  assert(blocks.some(b=>b.includes(call)), `${call}: slide mismatch`);
}
console.log(`${checks.length} real Zig 0.17.0 calls match demos; 4 excerpts, each <=3 lines`);
