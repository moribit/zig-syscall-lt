#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
python3 benchmarks/poll-epoll/run.py "$@"
