import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'

if (process.platform !== 'linux') throw new Error('Run on Linux. On this Mac: orb -m zig-syscall-lab node scripts/check-linux.mjs')
const zig = process.env.ZIG ?? 'zig'
function run(cmd, args, input) {
  const r = spawnSync(cmd, args, { input, encoding: 'utf8' })
  if (r.error || r.status !== 0) throw new Error(`${cmd} ${args.join(' ')}: ${r.error ?? r.stderr}`)
  return { stdout: r.stdout, stderr: r.stderr }
}
assert.equal(run(zig, ['version']).stdout.trim(), '0.17.0')
const dir = mkdtempSync(join(tmpdir(), 'zig-io-lt-'))
try {
  const results = { checkedAt: new Date().toISOString(), kernel: run('uname', ['-srmo']).stdout.trim(), zig: '0.17.0', programs: {} }
  for (const name of ['raw_write', 'raw_read', 'io_basic', 'io_injection', 'io_uring_read']) {
    const binary = join(dir, name)
    run(zig, ['build-exe', `snippets/${name}.zig`, `-femit-bin=${binary}`])
    const r = run(binary, [], name === 'raw_read' ? 'read works\n' : undefined)
    if (name === 'raw_write' || name === 'io_basic' || name === 'io_injection') assert.equal(r.stdout, 'hello\n')
    if (name === 'raw_read') {
      assert.equal(r.stdout, 'read works\n')
      assert.equal(run(binary, [], 'abc'.repeat(100)).stdout, 'abc'.repeat(100))
      assert.equal(run(binary, [], '').stdout, '')
    }
    if (name === 'io_injection') assert.match(r.stderr, /Threaded: success\nfailing: InputOutput/)
    if (name === 'io_uring_read') assert.match(r.stderr, /user_data=42, res=128/)
    results.programs[name] = r
  }
  run('strace', ['-e', 'write', '-o', join(dir, 'write.trace'), join(dir, 'raw_write')])
  results.writeTrace = readFileSync(join(dir, 'write.trace'), 'utf8')
  assert.match(results.writeTrace, /write\(1, "hello\\n", 6\)\s*= 6/)
  // Keep direct io_uring evidence distinct from the std.Io.Evented demo.
  run('strace', ['-f', '-e', 'trace=io_uring_setup,io_uring_register,io_uring_enter', '-o', join(dir, 'uring.trace'), join(dir, 'io_uring_read')])
  results.uringTrace = readFileSync(join(dir, 'uring.trace'), 'utf8')
  assert.match(results.uringTrace, /io_uring_setup\(8,[^\n]*= \d+/)
  assert.match(results.uringTrace, /io_uring_enter\([^\n]*= 1/)
  writeFileSync('docs/validation-linux.json', JSON.stringify(results, null, 2) + '\n')
  console.log(JSON.stringify(results, null, 2))
} finally { rmSync(dir, { recursive: true, force: true }) }
