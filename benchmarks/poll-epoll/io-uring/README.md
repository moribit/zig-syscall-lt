# io_uring RECV / POLL_ADD比較

[測定前の設計](BENCHMARK_DESIGN.md) / [実測と限界](ANALYSIS.md)。既存poll/epoll/Adaptiveと過去の結果は保持し、新しい系列で全方式を再測定する。高速化を合否条件にしない。

## 環境と最小実行

Linux、Zig **0.17.0**、Python3、matplotlib、taskset、strace、readelfが必要。libc/liburingのリンクは不要。今回の環境はM2 MacBook Air / OrbStack Fedora aarch64。CPU2 affinityは物理CPU専有を保証しない。

```sh
# リポジトリのルートでLinux上から実行
zig version
zig build-exe benchmarks/poll-epoll/io-uring-probe.zig -O ReleaseFast -femit-bin=/tmp/uring-probe
/tmp/uring-probe
zig test benchmarks/poll-epoll/io-uring-tests.zig
zig test benchmarks/poll-epoll/io-uring-fault-tests.zig
zig test benchmarks/poll-epoll/tests.zig
zig build-exe benchmarks/poll-epoll/io-uring-main.zig -O ReleaseFast -femit-bin=/tmp/uring-bench
# backend N Ready payload bursts seed submit_batch SQ_entries CQ_copy_batch
/tmp/uring-bench uring 64 1 1024 32 17 64 64 64
# backend: poll / epoll / uring / uring-poll
```

Macから既存VMを使う例：

```sh
orb -m zig-syscall-lab sh -c 'cd /Users/mimoc/zig-syscall-lt && python3 benchmarks/poll-epoll/io-uring/run.py --output /tmp/uring-new'
```

CPU2が許可され、fd soft limit>=10000の環境を要求する。未対応時は理由を記録し性能値を生成しない。セキュリティ設定を変更せず、EPERMは原因を別途調べる。基本操作にio_uring_registerは不要で、probe用途だけで使用する。

## 構成

- `ring.zig`：Zig標準のABI/mmap/atomic実装を利用する薄い層。raw setup/enter、投入回数、overflow/dropped検査を追加。
- `recv.zig`：全fdへの初期要求、buffer所有、pending管理、RECVまたはoneshot POLL_ADD、終了cancel/終端CQE排出。
- `main.zig`：既存Workload/Poll/Epollを直接呼ぶ共通測定ループ。
- `probe.zig`：既知17byteのRECV・opcode probe。
- `tests.zig` / `fault-tests.zig`：正しさ検証。8+3テスト（rootを含む）と既存3テスト。
- `run.py`：動作ゲート・14条件×4方式の検査・warmup・本測定・環境記録。
- `analyze.py` / `report.py`：検証・CSV/SVG生成・公開レポート更新。
- `observe.py`：計時と分離したstrace観察。
- `capacity.py`：batch=64を固定したSQ64/Nの追加対照と再集計。

親ディレクトリの`io-uring-{main,probe,tests,fault-tests}.zig`は小さなentrypoint。Zigのmodule rootを既存workload等の親へ置き、同じソースをコピーせず利用するために設けている。

## 測定・再生成

```sh
python3 benchmarks/poll-epoll/io-uring/run.py --output /tmp/uring-new
python3 benchmarks/poll-epoll/io-uring/analyze.py /tmp/uring-new
# 保存済みの公開系列から再生成
python3 benchmarks/poll-epoll/io-uring/analyze.py
python3 benchmarks/poll-epoll/io-uring/capacity.py --analyze-only
python3 benchmarks/poll-epoll/io-uring/report.py
```

run.pyは既存rawを上書きしない。Linux、Zig版、CPU affinity、fd上限を確認後、probeと正しさ検査を通ってから測る。全条件の4バーストwarmupを先に完了し、本測定32バースト×10回。mainは152条件・本測定1520件、追加SQ容量対照は8条件・80件。mainのplan/scheduleを計時前に固定し、追加対照は別planに理由と条件を固定して保存した。

`observe.py`は`/tmp/zig-uring-bench`の指紋が保存済みmain環境と一致する場合だけ実行する。`capacity.py`も同じ凍結binaryを使い、既存capacity.jsonlへの上書きを拒否する。これらは公開済みmain系列用の操作で、新環境では`out`/binaryを新系列へ明示的に合わせる。結果を見て条件を選び直さない。

## データの仕様と比較範囲

raw各行には条件、実際のReady個数、seed/run、bursts、順序、時刻、コマンド、メッセージ/byte数、区間ns、CPU us、対象syscall件数を保存。

- `e2e_ns`：Producer開始から内容検証・次回rearmまで、32バーストの合計。
- `producer_ns` / `consumer_ns`：同じバースト窓を分割した合計。
- `submit_ns`：CQ batchごとのSQE準備+flush。`wait_ns`：API取得/索引変換またはCQコピー。時計費用を含む。小区間の中央値を加算して厳密に分解しない。
- `backend_init_ns`：poll配列、epoll ADD、またはring+buffer+全fd初期要求。`ring_setup_ns` / `mmap_ns` / `buffer_allocation_ns` / `initial_submit_ns`は内訳。
- `cancel_ns`：未完了要求のcancelと対象終端CQE/受付CQEの排出。`destroy_ns`：backend破棄。`workload_setup_ns`は共通socket生成。
- `user_us` / `system_us`：バーストループ外周のプロセスCPU。`lifetime_*`はsocket生成前からbackend破棄まで。socket closeやcommon buffer freeはこの後で、全process lifetimeではない。
- `enter_calls`：E2E内のenter試行数。初期投入・終了は別。`wait_calls` / `recv_calls` / `send_calls`も対象区間の試行数。時計等を含む全syscallではない。
- `sqes_submitted_including_initial`：初期要求とE2E内要求（cancelは除外）。`cqes`：E2Eの完了数。メッセージ数とは別。
- `cq_copy_calls`：空の取得試行も含む。`eintr`はpoll/recvと負CQE、enter内部再試行の個別件数は未出力。

`summary.csv`は全条件の中央値・最小最大・名目95%bootstrap帯・CPU・初期化込み値。`paired.csv`は同seed/runのepoll比。処理量が同じことを検証し、外れ値を除外しない。`capacity-summary.csv` / `capacity-paired.csv`は別系列。機能確認・strace結果は性能rawへ混ぜない。

`environment.json`にkernel、CPU、VM、OS、fd上限、Zig、最適化、libc有無、Git SHA、標準ライブラリ/測定ソース/binaryのSHA、負荷情報を記録。`source-snapshot/`から当時の実装を再ビルドできる。対応するZig 0.17.0の指紋を確認する。公開ソースの現行runnerには測定後の移植性改善があるため、実測時runnerもsnapshotに残した。

## 安全な要求寿命と限界

全N fdへ要求を投入し、将来のReady集合をConsumerへ渡さない。1fd1要求をpendingで守り、専用bufferを固定する。inactive要求は保持して次バーストに利用し、終了時だけcancelする。cancel受付だけでは解放せず、対象の終端まで回収する。

既存Aの同じReady状態を非消費で繰り返す指標と、POLL_ADDの再武装込みサイクルは直接比較しない。主図は送信・実受信込みB。RECVはsyscallを減らせてもキュー処理・投入・kernel仕事を持ち、常に高速ではない。SQ64の初期variantはbatch上限も64となるため、追加対照でbatch=64を揃えてSQだけを変更した。

SQPOLL、multishot、provided/registered buffers、fixed filesは未実施。性能は有限・送信先行バーストとVMの範囲に限る。別日の独立系列、物理Linux、継続到着、TCP/TLS、ホスト/kernel workerを含む全体CPUは今後の課題。

出典：[io_uring_enter(2)](https://man7.org/linux/man-pages/man2/io_uring_enter.2.html)、[io_uring_register(2)](https://man7.org/linux/man-pages/man2/io_uring_register.2.html)、[io_uring(7)](https://man7.org/linux/man-pages/man7/io_uring.7.html)。共有リングのrelease/acquireは実際の0.17.0 `std/os/linux/IoUring.zig`を調査し、独自に再発明していない。
