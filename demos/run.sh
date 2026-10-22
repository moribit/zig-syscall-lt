#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
case "${1:-}" in
  0|00|write) demo=00-write ;;
  1|01|blocking) demo=01-blocking ;;
  2|02|poll) demo=02-poll ;;
  3|03|epoll) demo=03-epoll ;;
  4|04|io-uring) demo=04-io-uring ;;
  *) echo 'Usage: sh demos/run.sh 0|1|2|3|4 [--source|--trace|--saved]' >&2; exit 2 ;;
esac
case "${2:-}" in
  --source)
    if command -v bat >/dev/null 2>&1; then exec bat --paging=never --style=plain --language=zig "demos/$demo.zig"; fi
    exec cat "demos/$demo.zig" ;;
  --saved) exec cat "demos/recordings/$demo.log" ;;
  ''|--trace) ;;
  *) echo 'Unknown option' >&2; exit 2 ;;
esac
[ "$(uname -s)" = Linux ] || { echo 'Linux required: enter OrbStack first.' >&2; exit 1; }
command -v timeout >/dev/null || { echo 'GNU timeout is required.' >&2; exit 1; }
binary="demos/.build/$demo"
[ -x "$binary" ] || { echo 'Run sh demos/check.sh first (prebuild all demos).' >&2; exit 1; }
if [ "${2:-}" = --trace ]; then
  case "$demo" in
    04-*) calls=io_uring_setup,io_uring_enter,io_uring_register,pipe2,read,write,close,mmap,munmap ;;
    *) calls=pipe2,poll,ppoll,epoll_create1,epoll_ctl,epoll_wait,epoll_pwait,read,write,close,clock_nanosleep,nanosleep ;;
  esac
  exec timeout --kill-after=2 12 "${STRACE:-strace}" -f -tt -T -e "trace=$calls" "$binary"
fi
exec timeout --kill-after=2 10 "$binary"
