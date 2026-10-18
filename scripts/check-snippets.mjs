import { readFileSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'

const zig = process.env.ZIG ?? 'zig'
function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', ...options })
  if (result.error) throw result.error
  if (result.status !== 0) throw new Error(`${command} ${args.join(' ')}\n${result.stderr || result.stdout}`)
  return result.stdout.trim()
}
if (run(zig, ['version']) !== '0.17.0') throw new Error('Use Zig 0.17.0 (or set ZIG to its executable).')

const markdown = readFileSync(new URL('../slides.md', import.meta.url), 'utf8')
const snippets = [...markdown.matchAll(/^```(zig|js)\s*\n([\s\S]*?)^```/gm)]
const temporary = mkdtempSync(join(tmpdir(), 'zig-slides-'))
let zigCount = 0
let jsCount = 0
try {
  for (const [index, match] of snippets.entries()) {
    const [, language, code] = match
    const filename = join(temporary, `snippet-${index}.${language === 'zig' ? 'zig' : 'mjs'}`)
    if (language === 'js') {
      writeFileSync(filename, code)
      run(process.execPath, ['--check', filename])
      jsCount++
      continue
    }
    let body = code
    if (code.includes('fn app(')) {
      body = `const std = @import("std");\n${code}\npub fn main(init: std.process.Init) !void { try app(init.io); }`
    } else if (code.includes('linux.read')) {
      body = `const linux = @import("std").os.linux;\npub fn main() void { var buf: [10]u8 = undefined;\n${code}\n_ = n; }`
    } else {
      body = `const std = @import("std");\npub fn main() void {\n${code}\n_ = n; }`
    }
    writeFileSync(filename, body)
    for (const target of ['x86_64-linux', 'aarch64-linux']) {
      run(zig, ['build-exe', filename, '-target', target, '-fno-emit-bin', '--cache-dir', join(temporary, 'cache'), '--global-cache-dir', join(temporary, 'global-cache')])
    }
    zigCount++
  }
  if (zigCount !== 3 || jsCount !== 1) throw new Error(`Unexpected snippet count: Zig=${zigCount}, JS=${jsCount}. Review the validation wrappers.`)
  for (const filename of ['raw_write.zig', 'raw_read.zig', 'io_basic.zig', 'io_injection.zig', 'io_uring_read.zig']) {
    for (const target of ['x86_64-linux', 'aarch64-linux']) {
      run(zig, ['build-exe', new URL(`../snippets/${filename}`, import.meta.url).pathname, '-target', target, '-fno-emit-bin', '--cache-dir', join(temporary, 'cache'), '--global-cache-dir', join(temporary, 'global-cache')])
    }
  }
  console.log(`Zig 0.17.0: ${zigCount} slide snippets and 5 complete programs compiled for both Linux targets. ${jsCount} JS snippet passed syntax checks.`)
} finally {
  rmSync(temporary, { recursive: true, force: true })
}
