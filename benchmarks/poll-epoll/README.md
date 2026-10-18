# poll / epoll比較実験（Zig 0.17.0 / Linux）

同じnon-blocking Unix Domain Socketのsocketpair集合で、pollとLevel-triggered epollを比較し、条件成立後にAdaptiveを評価する合成ベンチマーク。std.Io.Eventedは使用しない。性能が逆転することやAdaptiveが速くなることを成功条件にしない。

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
| adaptive.zig / run-adaptive.py | 校正コストモデルを使う切替と動的負荷 |
| analyze-adaptive.py | Adaptiveの検証、集計、Oracle、図D |
| metrics.zig | raw syscallエラー、MONOTONIC時刻、getrusage |
| tests.zig | Ready集合・EOF・EAGAIN・EINTR・解除・解放のテスト |
| run.py / run.sh | ReleaseFastビルド、ランダムなペア測定、生データ保存 |
| validate.py | 保存sampleの件数・byte・メッセージ・イベント整合性 |
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

### B：バースト型End-to-Endと受信区間

- 同じConsumer 1スレッドで、Producerの送信開始から全受信・内容検査完了までを`e2e_duration_ns`に積算する。Producerは共通のfill()、Consumerも共通のreceive()を使う。
- 同時に送信側のproducer_nsと受信側のduration_nsを分離して記録し、API取得コストが送信処理に隠れる影響を把握する。
- 初回fixed / replicationは送信済みバーストの受信区間のみを記録した予備系列。送信込みの正式なB比較はend-to-end / end-to-end-replication / crossover-checkで、予備系列をEnd-to-Endと呼ばない。
- 1fdあたりの読み取り予算は1payload、イベント容量は両方式ともN。部分受信なら残量を読み、EAGAINは再通知に委ねる。EINTRは再試行。送信も部分成功、EAGAIN、EINTRを処理し、MSG_NOSIGNALを使う。
- HUP/ERRも取り出してrecvで結果を確認する。EOFが目標より早ければ失敗。期限超過は失敗で、永久待ちしない。
- ストリームの既知のpayload長を各fdで受信し終えると1メッセージと数える。内容もroundごとのパターンと照合する。
- Ready率は投入直後のready_fds/N。受信で減少し、受信完了まで新しい送信はしない。投入先fd集合は生成側が管理する。

両方式は同じ生成ロジック・fd配置seed・payload・予算を使用。Webサーバの継続的な並行到着を再現するものではない。Bの1024fd/全Ready/64 BではProducerが総時間の約47〜51%で、差を覆い隠す。このため、Aと受信区間の比較も併用し、送信側に支配された総スループットから待機APIだけの速度を推論しない。

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
python3 benchmarks/poll-epoll/validate.py
python3 benchmarks/poll-epoll/analyze.py benchmarks/poll-epoll/results/fixed
python3 benchmarks/poll-epoll/analyze.py benchmarks/poll-epoll/results/replication
python3 benchmarks/poll-epoll/analyze.py benchmarks/poll-epoll/results/end-to-end
python3 benchmarks/poll-epoll/analyze-adaptive.py /tmp/adaptive-new
```

- environment.json：uname、lscpu、OS、Zig、Git SHAとdirty状態、VM区分、fd上限、最適化、条件、seed。
- raw.jsonl：1行1sample。backend、benchmark、fds、ready_fds、requested_ready_percent、ready_ratio、payload、iterations、run、warmup、seed。
- duration_ns：Aは検査込みの取得反復時間、Bはバースト受信区間の積算。
- e2e_duration_ns / producer_ns：送信開始〜受信完了と、送信区間の積算。受信だけの予備系列にはない。e2e_user_us / e2e_system_usは送信を含めたCPU時間。
- acquisition_ns：待機API＋索引取得の積算。`/wait_calls`が1取得、`/events_observed`が1通知の時間。
- messages / bytes_received / bytes_sent：Bの完了メッセージ・受信・送信量。Aは受信せずmessages=0、初期送信量のみを記録。
- user_us / system_us：getrusage差分を測定区間ごとに積算。低粒度の短い区間は0になり得る。時刻取得・検査や計測用getrusage境界の負担も含む。プロセス全体のCPU時間ではない。
- wait_calls / recv_calls / send_calls：呼び出し箇所で数えた回数（EINTR再試行も含む）。**全syscall総数ではない。** socket生成、close、登録、時計、getrusage等は別。send_callsは測定外のProducer。
- errors / eintr / eagain：予期しない失敗は中断、通常成功sampleのerrorsは0。EINTR/EAGAINは扱った回数。
- summary.csv：条件別の中央値、Q1/Q3、最小、最大、測定数。messages_s / bytes_sは受信区間、e2e_messages_sは送信込み区間を分母にする。図Cは使用した系列に応じてprefilled receiveまたはburst end-to-endと明記。
- analysis.json：同seed/runのペア比（poll/epoll）の中央値、bootstrap 95%区間（4000回、固定seed）、勝者分類、Oracleの結果。
- A-fds.svg / B-ready.svg：実験A、C-throughput.svg：実験B、D-adaptive.svg：動的負荷。混在した曲線を作らない。軸は0始まり、帯はIQR、色はpoll=青、epoll=茶。

## 結果とAdaptiveの判断

初回のA/受信区間系列fixedは1280本測定＋128 warmup。別seedのreplicationは480＋48。送信込みBのend-to-endは640＋64、代表条件のend-to-end-replicationは240＋24、逆転条件のcrossover-checkは40＋4。Adaptive動的評価は30＋3。計2710本測定で、Ready集合または送受信byte数・内容を検査した。

1024 fd・64 B、各方式n=10の中央値：

| 測定 | Ready | poll | epoll |
| --- | --- | --- | --- |
| A：取得時間/回 | 10/1024（約1%） | 42.19 µs | 0.231 µs |
| A：取得時間/回 | 1024/1024 | 42.56 µs | 16.46 µs |
| B：送信〜受信完了のmsg/s | 10/1024 | 0.213 M | 2.719 M |
| B：送信〜受信完了のmsg/s | 1024/1024 | 1.939 M | 2.066 M |

低Ready率でepoll優位、高Ready率で差が縮小した。予備系列では逆転がなかったが、送信込みでは4096fd/全Ready/1KiBでpoll優位が独立の2系列に出た。end-to-end-replicationのペア比中央値poll/epoll=0.9806、95%区間0.9624〜0.9920。その後のcrossover-checkも同方向。これを受けAdaptive実装へ進んだ。最初の系列で同じ優位が出ていなかったことも保存し、結果を隠したり望む値へ調整したりしていない。

### Adaptiveの実装・校正・動的評価

```sh
# コストモデルの入力を独立に校正（保存済み系列で再分析可能）
sh benchmarks/poll-epoll/run.sh --receive-only --fds 4096 --payload 1024 --ready 1,100 \
  --seed 20261021 --output /tmp/crossover-check
# 保存済みcrossover-checkのrun1..5を訓練データに使う
python3 benchmarks/poll-epoll/run-adaptive.py --output /tmp/adaptive-new
python3 benchmarks/poll-epoll/analyze-adaptive.py /tmp/adaptive-new
```

固定方式の初期Oracleは条件ごとの前半で方式を選び後半で評価。動的負荷のOracleも固定方式の前半データからPhaseごとの方式を選び、後半で評価する。後者はepoll→poll→epollを選び、切替費用を無視した改善余地は約0.80%。実運用アルゴリズムではない。

Adaptiveのモデルはcrossover-checkのrun1..5だけを使用。1%と100%の1バースト費用を観測完了fd数で線形補間し、EMA係数1/4、最低継続16バースト、32バーストで切替推定費用の1.1倍を回収できる場合だけ切り替える。動的評価を見た後のチューニングはしていない。

Ready率推定のための追加pollは呼ばない。Nまで取得できる配列と、実際に受信完了したfd数を使う。切替は全受信済みの境界でepollをcloseし、戻すときに全fdを再登録。poll期間もepollを登録し続けるとProducerがReady List維持費用を払ってしまうため、それを避ける。切替・推定・判定費用を測定に含める。初期登録はsetup_nsに分離し、初期登録込みの速度も集計する。

負荷は4096fd、1KiB、1%→100%→1%、各200ms。方式順を乱択し各方式warmup1＋本測定10。Phase継続時間を同じにするため、速い方式はより多くのバーストを完了する。処理量の異なる固定ジョブの総時間比較ではなく、同じ時間制御負荷でのmsg/s比較。

| 動的負荷 | msg/s中央値 | 切替回数中央値 | 切替時間中央値 |
| --- | --- | --- | --- |
| poll固定 | 0.312 M | 0 | 0 |
| epoll固定 | 1.076 M | 0 | 0 |
| Adaptive | 1.074 M | 2 | 2.130 ms |

Adaptive/epollのペア比改善率中央値は-0.40%、bootstrap95%区間は-1.61〜+2.48%。**この方式・負荷では改善を確認できなかった。** 悪化も断定しない。移行の遅れ、再登録費用、モデル誤差があり、固定方式の小さな逆転だけでは改善を保証しない。

## 正しさとstrace

テストは1/複数fd、0/全Ready、同一fdへのLT再通知、部分消費、空ソケットのEAGAIN、Producer終了後のデータ・EOF、解除後に通知されないこと、close後のEBADFを確認する。SIGUSR1を待機中のスレッドへ実際に送り、両バックエンドがEINTRを再試行することも検証する。Adaptiveは別に最低継続時間のテストを行い、動的評価全sampleで各fdの受信、byte数、重複通知、Phase完了を検査する。

```sh
strace -c -e trace=ppoll,poll,epoll_pwait,epoll_wait,epoll_ctl,recvfrom,sendto \
  /tmp/poll-epoll-bench epoll receive 64 6 64 8 17
```

results/poll-strace.txtとepoll-strace.txtは動作確認専用。両方でwait=8、send=48、recv=48、epollの登録=64を確認した。straceで得られた時間は通常の性能表・グラフへ入れない。

## 限界と今後

- Bはバースト型の送信開始〜受信完了。並行Producerの継続到着は再現していない。受信だけの予備系列と混同しない。
- Aは固定Ready集合の繰り返し通知。新規通信のイベントを1回ずつ処理する実験ではない。
- 初期登録費用は分離。動的切替のclose/再登録費用は含めたが、任意の並行到着中の切替や短命な接続は未検証。
- イベント容量N、1fdあたり1payloadの予算。小さいmaxeventsやスケジューラ変更の効果は未検証。
- 本測定にEAGAIN/EINTRがなくても、その処理の正しさは別テストで確認する。送信のOSレベルの部分書き込みを強制したケースは未検証。
- 信頼区間は少数sampleからの推定で、多重比較の調整なし。小差を断定しない。別CPU・カーネル・最適化・bare metalで再確認が必要。

参考：[poll(2)](https://man7.org/linux/man-pages/man2/poll.2.html)、[epoll(7)](https://man7.org/linux/man-pages/man7/epoll.7.html)、[epoll_wait(2)](https://man7.org/linux/man-pages/man2/epoll_wait.2.html)、Zig 0.17.0配布のlib/std/os/linux.zig。

デモ用のSVGをSlidevへ同期する場合は、実験AのB-ready.svg、送信込みBのC-throughput.svg、AdaptiveのD-adaptive.svgを使用する。

```sh
cp benchmarks/poll-epoll/results/fixed/B-ready.svg public/benchmarks/
cp benchmarks/poll-epoll/results/end-to-end/C-throughput.svg public/benchmarks/
cp benchmarks/poll-epoll/results/adaptive/D-adaptive.svg public/benchmarks/
```
