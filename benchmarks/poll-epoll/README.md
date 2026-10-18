# poll / epoll比較実験（Zig 0.17.0 / Linux）

同じnon-blocking Unix Domain Socketのsocketpair集合で、pollとLevel-triggered epollを比較する合成ベンチマーク。std.Io.Eventedは使用しない。性能が逆転することやAdaptiveが速くなることを成功条件にしない。

## 目的・仮説

1. 監視fdが多くReady率が低いとepollが有利になる。
2. 高Ready率では差が縮小し、逆転する可能性もある。
3. 動的な切り替えは改善余地がある場合に限り検討する。切り替えコストで悪化し得る。

pollは毎回fd配列を渡し、reventsを走査する。epollは事前に登録した集合のReadyイベントを取得する。どちらも「読み取り可能」等を通知し、受信はアプリ側で行う。

## 構成

| ファイル | 役割 |
| --- | --- |
| main.zig | 共通の測定・データ照合・JSON出力 |
| workload.zig | socketpair生成、固定seedでfd配置、共通の送受信 |
| poll.zig / epoll.zig | 同じイベント容量・インターフェースの固定方式 |
| metrics.zig | raw syscallエラー、MONOTONIC時刻、getrusage |
| tests.zig | Ready集合・EOF・EAGAIN・EINTR・解除・解放のテスト |
| run.py / run.sh | ReleaseFastビルド、ランダムなペア測定、生データ保存 |
| analyze.py | 検証、統計表、ペア比較、Oracle、SVG生成 |
| results/ | 独立した測定系列、集計、グラフ、動作観察用strace |

## 環境構築とビルド

[Zig公式配布](https://ziglang.org/download/)の0.17.0を用意する。LinuxとPython 3、図の再生成にはMatplotlibが必要。今回のLinux VMではFedoraのpython3-matplotlibを導入した。一般的な環境では仮想環境に`pip install matplotlib`でもよい。

```sh
zig version  # 0.17.0
ulimit -n    # 4096組なら8192 fd以上。実行前チェックは8224以上
zig build-exe benchmarks/poll-epoll/main.zig -O ReleaseFast -femit-bin=/tmp/poll-epoll-bench
zig test benchmarks/poll-epoll/tests.zig
```

このMacでは`orb -m zig-syscall-lab`でLinuxへ入る。macOSで直接実行しない。aarch64 LinuxではZigのlinux.pollはppoll、linux.epoll_waitはepoll_pwaitへ変換される。実在する0.17.0配布ソースでシグネチャを確認した。

## 単独実行

```sh
# backend mode fds ready_fds payload iterations seed
/tmp/poll-epoll-bench poll readiness 1024 10 64 1000 17
/tmp/poll-epoll-bench epoll receive 1024 10 64 256 17
```

fd数、Ready **個数**、payload（64 / 1024 byte）、反復数、seedを指定する。0 Readyはreadinessのみ対応。異常な引数、リソース不足、予期しないEOF、破損、5秒の送受信上限超過などは非ゼロで終了する。結果を失敗サンプルとして平均へ混ぜない。

## 測定の定義

### A：readiness取得

- 送信して固定したfd集合をReadyにし、データを消費せずtimeout=0を反復する。
- 両方ともイベント出力容量は監視fd数N。epollのmaxevents切り詰めがない。
- `acquisition_ns`は待機APIと戻りイベントの索引取得（pollのrevents全走査、epollのイベント配列走査）まで。生のsyscallだけの時間ではない。
- Ready集合の正当性検査はacquisitionの外。`duration_ns`には検査も含む。
- 送信、socket作成、epoll登録は測定区間外。`setup_ns`に登録等の初期化時間を別記。
- 常時Readyな同じfdを再通知で何度も観測する。events_observedは新しい通信メッセージ数ではない。

### B：送信済みバーストの受信完了

- Producerは同一スレッドで反復ごとにReady対象fdへ1メッセージを送信する。送信が終わってから測定を開始する。
- 受信開始からそのバーストの全データ受信・内容検査までをdurationとして積算。Producer送信時間、バースト間隔は除外する。
- **送信開始からの完全なEnd-to-End性能や、ProducerとConsumerの同時実行性能ではない。** 図Cも「prefilled burst receive」と明記する。生データのbenchmark名はreceive。
- 1fdあたりの読み取り予算は1payload、イベント容量は両方式ともN。recvが部分成功なら残量を読み、EAGAINは再通知に委ねる。EINTRは再試行。送信も部分成功、EAGAIN、EINTRを処理する。MSG_NOSIGNALを使用。
- HUP/ERRもイベントとして取り出してrecvで結果を確認する。EOFが受信目標より早ければ失敗。期限超過も失敗とし、永久待ちしない。
- ストリームにメッセージ境界はない。各fdの既知のpayload長を受信し終えたときに1メッセージと数える。内容はroundごとのパターンとも照合する。
- Ready率は投入直後の`ready_fds/N`。受信で減少し、受信完了まで新しい送信はしない。

両方式は同じ生成ロジック・fd配置seed・payload・予算を使用。常時並行のWebサーバのイベント到着、接続の増減、ネットワーク遅延を再現しない。

## 全条件・再測定

```sh
sh benchmarks/poll-epoll/run.sh --output /tmp/poll-epoll-run
# このMacから
orb -m zig-syscall-lab sh benchmarks/poll-epoll/run.sh --output /tmp/poll-epoll-run
# 別seedで代表条件を再測定
sh benchmarks/poll-epoll/run.sh --focus --seed 20261020 --output /tmp/poll-epoll-replication
```

既存のraw.jsonlがあれば停止して上書きを防ぐ。計測中に他のベンチマーク、依存関係のインストールなどを同時実行しない。

| 条件 | 値 |
| --- | --- |
| 監視fd | 64 / 256 / 1024 / 4096（socketpairは2 fdずつ） |
| 要求Ready率 | 1 / 10 / 50 / 100% |
| 実Ready数 | `max(1, round(N × ratio))`。実率も保存 |
| payload | 64 B / 1024 B |
| 方式 | poll / epoll LT |
| ウォームアップ | 各条件・方式1回（保存するが集計から除外） |
| 本測定 | 各条件・方式10回、独立プロセス |
| A反復 | 1000回/sample |
| Bバースト数 | `max(8, min(256, floor(16384/ready_fds)))`。同じ条件の両方式で同数 |
| 順序 | 条件ペアをshuffle、ペア内の方式順も乱択 |
| 構成 | Consumer 1スレッド。CPU affinity未固定 |
| 最適化 | ReleaseFast |

FD上限に適合しない場合は測定前に終了する。今回は上限1,048,576で全条件を実行できた。CPUモデルはVM内ではAppleベンダー／モデル名未公開、論理CPU8。環境の完全な出力は各系列のenvironment.jsonに記録した。VMとホストの他処理、周波数・スケジューリングの影響が残る。

## データ仕様と再分析

```sh
python3 benchmarks/poll-epoll/analyze.py benchmarks/poll-epoll/results/fixed
python3 benchmarks/poll-epoll/analyze.py benchmarks/poll-epoll/results/replication
```

- environment.json：uname、lscpu、OS、Zig、Git SHAとdirty状態、VM区分、fd上限、最適化、条件、seed。
- raw.jsonl：1行1sample。backend、benchmark、fds、ready_fds、requested_ready_percent、ready_ratio、payload、iterations、run、warmup、seed。
- duration_ns：Aは検査込みの取得反復時間、Bはバースト受信区間の積算。
- acquisition_ns：待機API＋索引取得の積算。`/wait_calls`が1取得、`/events_observed`が1通知の時間。
- messages / bytes_received / bytes_sent：Bの完了メッセージ・受信・送信量。Aは受信せずmessages=0、初期送信量のみを記録。
- user_us / system_us：getrusage差分を測定区間ごとに積算。低粒度の短い区間は0になり得る。時刻取得・検査や計測用getrusage境界の負担も含む。プロセス全体のCPU時間ではない。
- wait_calls / recv_calls / send_calls：呼び出し箇所で数えた回数（EINTR再試行も含む）。**全syscall総数ではない。** socket生成、close、登録、時計、getrusage等は別。send_callsは測定外のProducer。
- errors / eintr / eagain：予期しない失敗は中断、通常成功sampleのerrorsは0。EINTR/EAGAINは扱った回数。
- summary.csv：条件別の中央値、Q1/Q3、最小、最大、測定数。messages/sとbytes/sは受信区間のみを分母にする。
- analysis.json：同seed/runのペア比（poll/epoll）の中央値、bootstrap 95%区間（4000回、固定seed）、勝者分類、Oracleの結果。
- A-fds.svg / B-ready.svg：実験A、C-throughput.svg：実験B。混在した曲線を作らない。軸は0始まり、帯はIQR、色はpoll=青、epoll=茶。

## 結果とAdaptiveの判断

初回系列fixedは1280本測定sample＋128 warmup。別seedのreplicationは480本測定sample＋48 warmup（64/1024/4096 fd、1/100%）。全sampleでReady集合または送受信byte数・内容の整合性を確認した。

1024 fd・64 Bの初回中央値（各方式n=10）：

| 測定 | Ready | poll | epoll |
| --- | --- | --- | --- |
| A：取得時間/回 | 10/1024（約1%） | 42.19 µs | 0.231 µs |
| A：取得時間/回 | 1024/1024 | 42.56 µs | 16.46 µs |
| B：受信メッセージ/s | 10/1024 | 0.221 M | 5.136 M |
| B：受信メッセージ/s | 1024/1024 | 3.668 M | 4.026 M |

低Ready率でepoll優位、高Ready率で差が縮小した。初回64条件比較のうち62条件でペア比95%区間がepoll優位、2条件は区間が1を含み不確実。poll優位の中央値はなく、測定誤差を超えた逆転は確認できなかった。代表条件の再測定24条件でもepoll優位で、1024 fd/100%/64 Bの受信はpoll=3.714 M、epoll=4.154 M msg/s。これはこのVM・この合成負荷の結果であり、pollが常に遅いことの証明ではない。

Oracleは条件を同じ重みで扱い、前半runで選んだ方式を後半runで評価。後半データを見て最小値を選ぶ楽観モデルも算出した。両系列・両実験とも最速固定epollに対する改善余地は0%。このモデルは切り替え費用を無視したオフライン比較基準であり、実運用アルゴリズムではない。

したがって**Adaptiveは未実装**。受信負荷で双方向の優位が確認できないため、移動平均・ヒステリシス・最低継続時間のチューニングや動的Phase負荷の評価には進んでいない。架空の切り替え回数・時間・改善値は作らない。今回の結果から「常にepollが最適」と一般化もしない。

## 正しさとstrace

テストは1/複数fd、0/全Ready、同一fdへのLT再通知、部分消費、空ソケットのEAGAIN、Producer終了後のデータ・EOF、解除後に通知されないこと、close後のEBADFを確認する。SIGUSR1を待機中のスレッドへ実際に送り、両バックエンドがEINTRを再試行することも検証する。Adaptive切替のテストは未実装のため非該当。

```sh
strace -c -e trace=ppoll,poll,epoll_pwait,epoll_wait,epoll_ctl,recvfrom,sendto \
  /tmp/poll-epoll-bench epoll receive 64 6 64 8 17
```

results/poll-strace.txtとepoll-strace.txtは動作確認専用。両方でwait=8、send=48、recv=48、epollの登録=64を確認した。straceで得られた時間は通常の性能表・グラフへ入れない。

## 限界と今後

- Bはprefill済み受信であり完全な送受信End-to-Endではない。並行Producerや時間変化する到着率は別実験が必要。
- Aは固定Ready集合の繰り返し通知。新規通信のイベントを1回ずつ処理する実験ではない。
- 初期登録費用は分離。短命な接続や頻繁な追加/削除でのトレードオフを評価していない。
- イベント容量N、1fdあたり1payloadの予算。小さいmaxeventsやスケジューラ変更の効果は未検証。
- 本測定にEAGAIN/EINTRがなくても、その処理の正しさは別テストで確認する。送信のOSレベルの部分書き込みを強制したケースは未検証。
- 信頼区間は少数sampleからの推定で、多重比較の調整なし。小差を断定しない。別CPU・カーネル・最適化・bare metalで再確認が必要。

参考：[poll(2)](https://man7.org/linux/man-pages/man2/poll.2.html)、[epoll(7)](https://man7.org/linux/man-pages/man7/epoll.7.html)、[epoll_wait(2)](https://man7.org/linux/man-pages/man2/epoll_wait.2.html)、Zig 0.17.0配布のlib/std/os/linux.zig。
