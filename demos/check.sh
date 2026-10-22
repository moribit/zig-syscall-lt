#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
fail() { echo "[FAIL] $*" >&2; exit 1; }
[ "$(uname -s)" = Linux ] || fail 'Linux required. Enter OrbStack: orb -m zig-syscall-lab'
command -v zig >/dev/null || fail 'zig not found; add Zig 0.17.0 to PATH'
[ "$(zig version)" = 0.17.0 ] || fail 'Zig 0.17.0 required'
for tool in timeout readelf; do command -v "$tool" >/dev/null || fail "$tool is required"; done
command -v "${STRACE:-strace}" >/dev/null || fail 'strace required (or set STRACE=/path/to/strace)'
repeats=${DEMO_REPEATS:-20}
case "$repeats" in ''|*[!0-9]*|0) fail 'DEMO_REPEATS must be a positive integer' ;; esac
out=${DEMO_CHECK_OUTPUT:-demos/.build/check}
[ ! -e "$out" ] || fail "Output exists: $out (choose a fresh DEMO_CHECK_OUTPUT)"
mkdir -p demos/.build "$out"
{ date -u; uname -a; zig version; git rev-parse HEAD; cat /etc/os-release; printf 'io_uring_disabled='; cat /proc/sys/kernel/io_uring_disabled 2>/dev/null || true; grep -E '^(Seccomp|NoNewPrivs):' /proc/self/status; } > "$out/environment.txt"
: > "$out/summary.tsv"
for source in demos/0*.zig; do
  name=$(basename "$source" .zig)
  echo "[build] $name"
  zig build-exe "$source" -O ReleaseSafe -femit-bin="demos/.build/$name" > "$out/$name-build.log" 2>&1 || { cat "$out/$name-build.log" >&2; fail "$name compile"; }
  readelf -lW "demos/.build/$name" > "$out/$name-elf.txt"
  readelf -dW "demos/.build/$name" >> "$out/$name-elf.txt"
  if grep -E 'INTERP|NEEDED' "$out/$name-elf.txt" >/dev/null; then fail "$name unexpectedly links a shared library"; fi
  sha256sum "$source" "demos/.build/$name" >> "$out/sha256.txt"
  i=1
  while [ "$i" -le "$repeats" ]; do
    log="$out/$name-$i.log"
    timeout --kill-after=2 10 "demos/.build/$name" > "$log" 2>&1 || { cat "$log" >&2; fail "$name run $i (timeout, SIGALRM, or syscall failure; io_uring: inspect setup error / seccomp / kernel policy)"; }
    case "$name" in
      00-*) grep -q '^hello$' "$log" && grep -q 'requested=6, returned=6' "$log" || fail 'write output' ;;
      01-*) grep -q 'waiting for data' "$log" && grep -q 'returned=5, buffer=hello' "$log" || fail 'blocking output' ;;
      02-*) grep -q 'EAGAIN' "$log" && grep -q 'ready: fd' "$log" && grep -q 'returned=5, buffer=hello' "$log" || fail 'poll output' ;;
      03-*) [ "$(grep -c 'ADD fd' "$log")" = 2 ] && grep -q 'ready: fd' "$log" && grep -q 'buffer=hello' "$log" || fail 'epoll output' ;;
      04-*) grep -q '\[SQE\] READ fd' "$log" && grep -q '\[CQE\] user_data=42, res=5' "$log" && grep -q '\[buffer\] hello' "$log" || fail 'io_uring completion' ;;
    esac
    printf '%s\t%s\tPASS\n' "$name" "$i" >> "$out/summary.tsv"
    i=$((i + 1))
  done
  case "$name" in
    04-*) calls=io_uring_setup,io_uring_enter,io_uring_register,pipe2,read,write,close,mmap,munmap ;;
    *) calls=pipe2,poll,ppoll,epoll_create1,epoll_ctl,epoll_wait,epoll_pwait,read,write,close,nanosleep,clock_nanosleep ;;
  esac
  timeout --kill-after=2 12 "${STRACE:-strace}" -f -tt -T -o "$out/$name.strace" -e "trace=$calls" "demos/.build/$name" > "$out/$name-traced.log" 2>&1 || fail "$name strace"
  case "$name" in
    00-*) grep -q 'write(1, "hello\\n", 6) *= 6' "$out/$name.strace" || fail 'write syscall missing' ;;
    01-*) grep -q 'read(' "$out/$name.strace" || fail 'read syscall missing' ;;
    02-*) grep -E 'p?poll\(' "$out/$name.strace" >/dev/null || fail 'poll syscall missing' ;;
    03-*) grep -q 'EPOLL_CTL_ADD' "$out/$name.strace" && grep -E 'epoll_(pwait|wait)\(' "$out/$name.strace" >/dev/null || fail 'epoll syscalls missing' ;;
    04-*) grep -q 'io_uring_setup(' "$out/$name.strace" && grep -q 'io_uring_enter(' "$out/$name.strace" || fail 'io_uring syscalls missing' ;;
  esac
  echo "[PASS] $name: $repeats independent runs + strace; no libc/liburing dynamic dependency"
done
printf 'repeats=%s\n' "$repeats" > "$out/COMPLETE"
echo "[PASS] all demos; evidence: $out"
