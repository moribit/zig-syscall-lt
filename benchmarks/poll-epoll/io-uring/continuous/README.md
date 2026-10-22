# 継続到着型の受信実験（正しさ検証で停止中）

Zig 0.17.0、Linux、libc/liburingなし。既存バースト実験とは独立した実装。
[事前計画](../CONTINUOUS_DESIGN.md)と[調査結果](../CONTINUOUS_ANALYSIS.md)を先に読む。

**現在の実機 Linux 6.18.9 ではmultishotのEOF検証が未通過。性能値は未取得。**
epoll/oneshot/multishotを呼び分けるプログラムは実装したが、完成済みベンチマークとは扱わない。
カーネル・Zigの更新、実験中のsleep追加、EOF検証の省略で成功を装わない。

## ビルドと正しさ確認

リポジトリルートで実行する。CPU2/3は実機の別物理コア（SMT兄弟6/7）。
別環境では affinity と sibling topology を確認して指定する。

```sh
zig version # 0.17.0
ulimit -Sn 16384
zig test benchmarks/poll-epoll/continuous-tests.zig -O ReleaseFast
zig build-exe benchmarks/poll-epoll/continuous-main.zig -O ReleaseFast -femit-bin=/tmp/continuous-bench
python3 benchmarks/poll-epoll/io-uring/continuous/run.py correctness \
  --output /tmp/continuous-correctness-new --consumer-cpu 2 --producer-cpu 3
```

runnerは既存出力先を上書きしない。失敗時は停止し、`COMPLETE`を作成しない。
性能系列には同一Zigソースで完了した21シナリオのゲートが必要。
現在保存した失敗系列を `--correctness-gate` に渡しても拒否する。

単体CLIの引数:

```text
backend fds active payload rate duration_ms seed pattern batch consumerCPU producerCPU sendTimesPath
```

backend: `epoll | oneshot | multishot`、pattern: `uniform | burst | randomized`。
最後のパスは実際の送信開始MONOTONIC nsをlittle-endian u64列として保存（`-`は診断時のみ）。
runnerは同じ配列を全方式で取得し、測定終了後gzip保存する。
Producerの将来到着先はConsumerへ渡さない。レコードはヘッダー込みpayloadサイズ。
メッセージ件数と受信CQE件数は別々に記録する。

## EOF停止の追試

```sh
python3 benchmarks/poll-epoll/io-uring/continuous/diagnose.py \
  /tmp/continuous-bench /tmp/continuous-eof-new
```

64接続・全active・64B・burst・10,000 messages/s・200msを3seedで検証。
診断の経過時間やstrace中の時間は性能比較に使わない。
終了CQEを取得できない場合はwatchdogがsocketのPEEK状態を記録してabortする。
未完了要求のbufferを通常の解放経路へ流さず、失敗をプロセス終了として明示する。

## 探索と独立確認（ゲート通過後のみ）

```sh
python3 benchmarks/poll-epoll/io-uring/continuous/run.py exploration \
  --correctness-gate /tmp/continuous-correctness-new --output /tmp/continuous-explore-new
python3 benchmarks/poll-epoll/io-uring/continuous/analyze.py /tmp/continuous-explore-new \
  --select benchmarks/poll-epoll/io-uring/continuous/CONFIRMATION_PLAN.json --plots
# この時点で確認条件をコミットし、その後に新しい確認系列を開始する
python3 benchmarks/poll-epoll/io-uring/continuous/run.py confirmation \
  --correctness-gate /tmp/continuous-correctness-new \
  --confirmation-plan benchmarks/poll-epoll/io-uring/continuous/CONFIRMATION_PLAN.json \
  --output /tmp/continuous-confirm-new
python3 benchmarks/poll-epoll/io-uring/continuous/analyze.py /tmp/continuous-confirm-new --plots
```

探索は31条件、各方式warmup1＋本測定3回。確認は選択した条件で20回。
`batch`、`representative`も独立出力先を指定する。
SVG生成だけmatplotlibが必要。実行中に分析・描画を同じ測定機で並行実行しない。
OrbStackは別結果ディレクトリへ保存し、実機と混ぜない。

## 出力と再分析

* `environment.json`: OS/CPU/affinity/SMT/fd上限/ソースSHA/最適化条件。
* `plan.json` / `schedule.json`: 全条件と順序、seed、warmup区別。
* `raw.jsonl`: 1実行1行。成功・失敗、コマンド、負荷/温度/周波数、受信結果。
* `send-*.u64le.gz`: 実送信開始時刻。非圧縮データのSHAをrawに保存。
* `analysis.json` / `summary.csv` / `all-conditions.svg`: 完了系列から再生成。
* `correctness-gate.json`: 性能測定開始を許可した検証系列とソースハッシュ。

latencyは全レコードで計測し、完全復元と内容検証が終わった時刻を使う。
処理窓内件数、drain込み時間・件数、Producerの遅れ・EAGAINを別記する。
CPUはgetrusageのTHREADとSELF。カーネルworkerの全CPUを表すものではない。
時計取得コストの独立計測、長時間試験、全正しさ項目の網羅は未完了。

保存済み診断CSVの再生成:

```sh
python3 benchmarks/poll-epoll/io-uring/continuous/summarize_diagnostics.py \
  benchmarks/poll-epoll/io-uring/continuous/results/continuous-evidence-20261022
```
