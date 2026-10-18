import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
assert.equal(process.platform, 'linux', 'Run this check on Linux');
const zig = process.env.ZIG || 'zig';
function exec(command, args) {
  const r = spawnSync(command, args, { encoding: 'utf8' });
  if (r.error) throw r.error;
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}
assert.equal(exec(zig, ['version']).stdout.trim(), '0.17.0');
const dir = mkdtempSync(join(tmpdir(), 'zig-backends-'));
const report = { checkedAt: new Date().toISOString(), zig: '0.17.0', kernel: exec('uname', ['-srmo']).stdout.trim(), modifiedStandardLibrary: false, backends: {} };
try {
  const libDir = JSON.parse(exec(zig, ['env']).stdout.match(/\.lib_dir = ("[^"]+")/)[1]);
  report.standardLibrary = Object.fromEntries(['std/Io.zig', 'std/Io/Uring.zig'].map(p => [p, createHash('sha256').update(readFileSync(join(libDir, p))).digest('hex')]));
  for (const backend of ['threaded', 'evented']) {
    const prefix = join(dir, backend);
    const build = exec(zig, ['build', '--build-file', 'snippets/build.zig', `-Dbackend=${backend}`, '--prefix', prefix]);
    const result = { build };
    report.backends[backend] = result;
    if (build.status !== 0) {
      assert.equal(backend, 'evented');
      assert.match(build.stderr, /no field named 'processReplacePath' in struct 'Io.VTable'/);
      continue;
    }
    const trace = join(dir, `${backend}.trace`);
    const run = exec('strace', ['-f', '-e', 'trace=write,writev,io_uring_setup,io_uring_enter,io_uring_register', '-o', trace, join(prefix, 'bin/io_backend_demo')]);
    assert.equal(run.status, 0, run.stderr);
    assert.equal(run.stdout, 'Hello, World!\n');
    result.run = run;
    result.trace = readFileSync(trace, 'utf8');
    if (backend === 'threaded') assert.match(result.trace, /writev?\(1,/);
    else { assert.match(result.trace, /io_uring_setup\(/); assert.match(result.trace, /io_uring_enter\(/); }
  }
  report.comparisonCompleted = Boolean(report.backends.evented.run);
  writeFileSync('docs/validation-backends.json', JSON.stringify(report, null, 2)+'\n');
  console.log(report.comparisonCompleted ? 'Both backends ran and were traced.' : 'Threaded ran and was traced. Evented is blocked by the unmodified Zig 0.17.0 standard library compile error; no Evented syscall result is available.');
} finally { rmSync(dir, { recursive: true, force: true }); }
