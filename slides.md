---
theme: default
title: Zigで覗く、Linuxの非同期I/O
info: |
  Webエンジニア向け15分LT。非同期処理の裏側を調べ、epollとio_uring、Zigのstd.Ioを知る。
class: cover
layout: default
colorSchema: light
aspectRatio: 16/9
canvasWidth: 1100
transition: fade
duration: 15min
fonts:
  sans: 'Noto Sans JP'
  mono: 'JetBrains Mono'
  provider: none
drawings:
  enabled: false
download: false
exportFilename: zig-linux-async-io
---

<div class="eyebrow">LINUX ASYNC I/O / ZIG 0.17.0</div>

# Zigで覗く、<br>Linuxの非同期I/O

<div class="cover-sub">epollからio_uringまで</div>

<div class="cover-bottom">いつも使う async/await の、少し下へ。</div>

<!--
目安25秒。発表の目安は本編14分25秒＋操作の余白35秒。ノートの詳細は補足・質疑用とし、すべてを読み上げない。口頭のみで「hotoさんのPython非同期処理LTを見て、epollなどの裏側が気になった」と話す。hotoさんの発言内容や資料URLは未提供なので引用や推測を追加しない。専用スライドは作らない。
「さらに最近io_uringという名前を見かけたので、その仕組みをZigで確かめてみた」という調査の動機を共有する。Zigの文法講座ではなくLinuxのI/Oを知る話。
対象: Zig 0.17.0、Linux。公式0.17.0リリースと同梱ソースを照合。
https://ziglang.org/download/index.json
https://ziglang.org/download/0.17.0/release-notes.html
-->

---

<div class="eyebrow">01 / THE QUESTION</div>

# async/await の下では何が起きている？

```js
const response = await fetch(url);
const text = await response.text();
```

<div class="flow horizontal runtime-flow">
<div>JavaScript / Python<br><strong class="ref-operation">async/await</strong></div>
<span class="connector">→</span>
<div>Runtime<br><small>実行と再開を管理</small></div>
<span class="connector">→</span>
<div>Event Loop<br><small>I/O待機</small></div>
<span class="connector">→</span>
<div><strong>epoll / kqueue</strong><br><small>Kernelの機構を利用</small></div>
</div>

<p class="fine">ネットワークI/Oの実装例。言語・runtime・OS・操作によって経路は異なる。</p>

<div class="takeaway">普段使う非同期処理の下には、OSのI/O機構がある</div>

<!--
目安45秒。「awaitは便利。でも、待っている間は誰が何をしているのか気になった」。まず普段のコードを見せる。
図は典型的なネットワークI/Oの概念図。JS/Pythonを単一の実装として扱わない。await構文が直接epollを呼び出すわけではない。runtimeが非同期関数の継続を管理する。
libuvはLinuxのsocketでepoll、macOS/BSDでkqueue等を使う。ファイルI/Oは既定でthread poolを使う経路もある。PythonにはSelectorEventLoopとProactorEventLoopがあり、全非同期I/Oがevent loopやepollを使うという一般化をしない。
https://docs.libuv.org/en/v1.x/design.html
https://docs.libuv.org/en/v1.x/fs.html
https://docs.python.org/3/library/asyncio-eventloop.html#event-loop-implementations
https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/await
-->

---

<div class="eyebrow">02 / FOUND IN THE WILD</div>

# 最近よく聞く io_uring

<div class="adoption-list">
<div><h3>PostgreSQL 18</h3><p>新しい非同期I/O基盤。Linuxで <code>io_method = io_uring</code> を選択可能。</p></div>
<div><h3>Dragonfly</h3><p>Redis / Memcached互換データストア。LinuxのI/Oにio_uringを活用。</p></div>
<div><h3>Node.js / libuv</h3><p>ファイルI/Oへの採用の経緯。libuv 1.49以降は既定をthread poolへ戻した。</p></div>
</div>

<p class="fine">PostgreSQL 18の公式発表は新AIO全体で「一部の条件で最大3倍」。io_uring単独の効果ではない。</p>

<div class="takeaway">なぜ、これほどいろいろな技術で注目されているのか？</div>

<!--
目安45秒。「OSの話かと思ったら、いつものWeb技術スタックでも名前が出てきた」。採用例は3つだけ。
PostgreSQL18はworker / io_uring / syncを選べる。既定はworker。io_uringはLinux用でliburingを有効にしたビルドが必要。公式発表の最大3倍は特定のストレージ読み取りシナリオにおける新AIO基盤全体の説明。CPU、SSD、SQLなどの再現条件は発表記事だけでは分からない。io_uring vs workerの測定値として扱わない。
Dragonflyは公式のアーキテクチャ説明とSSD tieringの記事でio_uring、O_DIRECT、registered buffersの利用を確認。性能数値は引用しない。
libuvはv1.45.0でLinuxの一部ファイルI/Oに導入、v1.49.0から既定のthread poolへ戻した。明示的なUV_LOOP_USE_IO_URING_SQPOLL設定で利用する経路はある。Node.jsの全I/Oがio_uringを使うとは言わない。Nodeの同梱libuvのバージョンにも依存する。
https://www.postgresql.org/about/news/postgresql-18-released-3142/
https://www.postgresql.org/docs/18/runtime-config-resource.html#GUC-IO-METHOD
https://www.dragonflydb.io/guides/redis-and-dragonfly-architecture-comparison
https://www.dragonflydb.io/blog/dragonfly-ssd-data-tiering-community-announcement
https://docs.libuv.org/en/v1.x/fs.html
-->

---

<div class="eyebrow">03 / A TOOL FOR EXPLORING</div>

# ところで、Zigとは？

<p class="big-statement smaller">Cに近い低レイヤーを扱える<br><strong>システムプログラミング言語。</strong></p>

<div class="columns compact">
<div>

### 明示的に扱う設計
メモリの確保や解放、<br>リソースの寿命をコードで管理する。

</div>
<div>

### OSの近くを触りやすい
クロスコンパイルとCとの相互運用。<br>Linux syscallを呼ぶ標準ライブラリもある。

</div>
</div>

<div class="takeaway">今回はZigを使って、Linuxの仕組みを実際に観察してみる</div>

<!--
目安25秒。Zigを知らない人へ、この発表で必要な特徴だけを紹介。
手動のメモリ/リソース管理、クロスコンパイル、C ABI等との相互運用が特徴。他のシステム言語でもsyscallは呼べるため、Zigでしかできないとは説明しない。今回選んだ観察の道具として位置付ける。RustやGoとの優劣比較はしない。
標準ライブラリのstd.os.linuxはLinux固有。std.Ioは後半に紹介する別の抽象化の層。
https://ziglang.org/learn/overview/
https://ziglang.org/documentation/0.17.0/
-->

---

<div class="eyebrow">04 / FIRST DISCOVERY</div>

# Zigでシステムコールを試す

```zig
const n = std.os.linux.write(1, "hello\n", 6);
```

<div class="terminal-label">Zig 0.17.0 / Linux aarch64で実測</div>

```sh
$ strace -e write ./raw_write
write(1, "hello\n", 6) = 6
```

<div class="inline-defs"><span class="ref-fd"><b>1</b> fd：出力先</span><span class="ref-buffer"><b>"hello\n"</b> データ</span><span class="ref-result"><b>6</b> 要求byte数</span><span class="ref-result"><b>= 6 / n</b> 書けたbyte数</span></div>

<div class="takeaway">「標準出力へ6 byte書く」が、OSへの依頼として見えた</div>

<!--
目安45秒。「Zigの1行とstraceの表示が対応したのが最初の発見」。コードはmain内の抜粋。完全なプログラムはsnippets/raw_write.zig。
2026-10-18、Fedora44 / OrbStack zig-syscall-lab、Linux 7.0.14-orbstack-00380-ga7e0a2dc9535 aarch64、Zig0.17.0でコンパイル・実行。strace -e writeでwrite(1,"hello\n",6)=6を実測。stdoutのhelloとstraceのstderrを分離して保存した。
fdを青、データを緑、byte数/結果を紫、操作を茶で対応させる。
std.os.linux.writeの戻り値usizeにはrawエラーがエンコードされる。linux.errno(n)で判定する。libcのwriteのように-1とerrno変数を使うAPIとは異なる。成功しても要求より短く書くことがある。最小プログラムはShortWriteを検出し、read例はpartial writeを処理する。
https://man7.org/linux/man-pages/man2/write.2.html
Zig0.17.0同梱: lib/std/os/linux.zig のwrite / errno
-->

---

<div class="eyebrow">05 / SYSTEM CALL</div>

# システムコールは、OSへの依頼

<div class="syscall-map">
<div class="space-label">ユーザー空間</div><div class="flow-node">Application <small>普通の関数呼び出しは、この側で完結することもある</small></div>
<div class="space-label"></div><div class="boundary"><span class="ref-operation">write()</span> ↓ syscall境界</div>
<div class="space-label">カーネル空間</div><div class="flow-node">Linux Kernel <small>権限やfdを確認し、I/Oを処理する</small></div>
<div class="space-label"></div><div class="down-arrow">↓</div>
<div class="space-label">出力先</div><div class="flow-node">Terminal / File / Socket</div>
</div>

<div class="takeaway">同じ関数呼び出しに見えても、ここではカーネルへ処理を依頼する</div>

<!--
目安30秒。syscallはユーザー空間からカーネル機能へ入るインターフェース。通常の関数呼び出しと区別する。
writeにはその下のファイルシステムやドライバー等の処理がある。図は説明のための省略であり、Terminal/Fileが必ず独立したハードウェアやユーザー空間という意味ではない。
syscall境界の通過そのものと、別のスレッド/プロセスへのスケジューラーによるcontext switchは同義ではない。後の性能説明でも区別する。
https://man7.org/linux/man-pages/man2/syscalls.2.html
https://man7.org/linux/man-pages/man2/write.2.html
-->

---

<div class="eyebrow">06 / FILE DESCRIPTOR</div>

# fdは、プロセスが持つ番号

<div class="columns fd-table">
<div>

### このプロセスのfdテーブル

| fd | 接続先の例 |
| --- | --- |
| <span class="ref-fd">0</span> | 標準入力 stdin |
| <span class="ref-fd">1</span> | 標準出力 stdout |
| <span class="ref-fd">2</span> | 標準エラー stderr |
| <span class="ref-fd">3</span> | ファイル hello.txt |
| <span class="ref-fd">4</span> | socket / pipe |

</div>
<div>

```zig
const n = linux.read(0, &buf, buf.len);
```

<p><span class="ref-fd">0：どこから</span><br><span class="ref-buffer">buf：どこへ</span><br><span class="ref-result">n：実際に読めたbyte数</span></p>

read / writeは行単位ではなく、<br>byte列を扱う。

</div>
</div>

<div class="takeaway">fdはファイル専用ではない。socketやpipeも同じ番号の仕組みで扱う</div>

<!--
目安35秒。fd = file descriptor。番号の意味はプロセスごとのテーブル内で決まる。別プロセスのfd3が同じ対象とは限らない。
0/1/2は通常の起動時の割り当てであり、closeやdup、シェルのリダイレクトで付け替えられる。openしたファイルが必ず3になるわけでもない。表の4は例でありsocketとpipeの同時割り当てを意味しない。
コードは説明用のread1回分の抜粋。失敗の判定、EOF、EINTR、出力のpartial writeまで扱う完全な例はsnippets/raw_read.zig。readはバッファ長までを読み、戻り値がその時に読めたbyte数。readが0なら通常EOF。端末canonical modeの行バッファリングはread一般の性質ではない。
https://man7.org/linux/man-pages/man2/open.2.html
https://man7.org/linux/man-pages/man2/read.2.html
-->

---

<div class="eyebrow">07 / WAITING</div>

# データがまだないとき、どうする？

<div class="columns">
<div>

### Blocking
<div class="flow vertical"><div class="ref-operation">read(fd)</div><span>↓</span><div>データが来るまで待つ</div><span>↓</span><div>結果を返す</div></div>
<p class="fine">呼び出したスレッドは先へ進まない。<br>待機中にCPUを使い続ける、という意味ではない。</p>

</div>
<div>

### Non-blocking
<div class="flow vertical"><div class="ref-operation">read(fd)</div><span>↓</span><div>データがない</div><span>↓</span><div class="ref-operation">EAGAIN：今は読めない</div></div>
<p class="fine">EAGAIN自身は再開通知を予約しない。<br>即座に再試行し続けるとbusy loopになる。</p>

</div>
</div>

<div class="takeaway">たくさんのI/Oを効率よく待つには、別の仕組みが必要になる</div>

<!--
目安40秒。「読めないなら戻ればいい。でも、いつ再試行すればいい？」を次の問いにする。
図はデータが未到着のsocket/pipe等を想定した模式図。regular fileのO_NONBLOCKが同じ待機挙動になるとは言わない。Blocking readもEOFやエラーならデータを待たず戻る。EAGAIN/EWOULDBLOCKは「今は操作できない」結果であり、Promiseのpendingと同一のオブジェクトや再開機構ではない。
通常、blocking待機中のスレッドはOSがsleepさせる。CPU占有を減らすには、単なるreadの繰り返しではなく準備完了や操作完了を待つ仕組みが必要。
https://man7.org/linux/man-pages/man2/read.2.html
https://man7.org/linux/man-pages/man2/open.2.html
-->

---

<div class="eyebrow">08 / READINESS COST</div>

# pollとepollは、どちらが速い？

<p class="benchmark-scenario">1,024 fdのうち、<strong>読み取り可能なのは10 fd</strong>なら？</p>

<div class="benchmark-model">
<h3 class="bench-poll">poll：毎回fdの集合を渡す</h3>
<div class="flow horizontal"><div>1,024 fdの配列</div><span class="connector">→</span><div>全体を確認する</div><span class="connector">→</span><div>Readyな10 fd</div></div>
<h3 class="bench-epoll">epoll：監視対象を先に登録する</h3>
<div class="flow horizontal"><div>監視対象を登録</div><span class="connector">→</span><div>Ready List</div><span class="connector">→</span><div>Readyな10 fd</div></div>
</div>

<div class="takeaway">監視fd数だけでなく、Ready率でも取得のコストは変わる</div>
<p class="fine">Ready率 = 読み取り可能な監視fd数 / 監視fd総数。どちらも受信処理はアプリ側で行う。</p>

<!--
目安35秒。Non-blockingで全部を何度もreadする代わりに、読み取り可能なfdを待つ仕組みを使う。pollとepollはreadiness通知の方式。epollに登録する費用もあり、常に速いとは限らない、という問いから実験へ。
1024 fdのうち10 fdは0.9765625%。図は取得経路を簡略化した概念図で、epollが全処理O(1)という意味ではない。取得するReadyイベント数が増えればコピー・処理費用も増える。
今回の実験はnon-blocking Unix Domain Socketのsocketpair、Consumer 1スレッド。epollはLevel-triggeredで、読み取り可能な状態なら再通知される。
https://man7.org/linux/man-pages/man2/poll.2.html
https://man7.org/linux/man-pages/man7/epoll.7.html
https://man7.org/linux/man-pages/man2/epoll_wait.2.html
-->

---

<div class="eyebrow">09 / MEASURED COST</div>

# Zigで実測してみた

<div class="columns benchmark-charts">
<div><h3>A：読み取り可能なfdの取得</h3><img src="/benchmarks/B-ready.svg" alt="1024 fdでReady率別の取得時間。pollは約42µs、epollは約0.23〜16.46µs。中央値、各10回。" /></div>
<div><h3>B：送信開始から受信完了まで</h3><img src="/benchmarks/C-throughput.svg" alt="1024 fdで送信開始から受信完了までの速度。低Ready率ではepoll優位、高Ready率では差が縮小。" /></div>
</div>

<div class="benchmark-numbers"><span>全Ready時の完了速度：<b class="bench-poll">poll 1.94 M</b> ／ <b class="bench-epoll">epoll 2.07 M msg/s</b></span><small>中央値・各10回。送信時間を含むバースト型測定。差は約7%。</small></div>

<div class="takeaway">高Ready率で差は縮小。条件を変えると、小さな逆転もあった</div>
<p class="fine">OrbStack VM / Linux 7.0.14 aarch64 / Zig 0.17.0 ReleaseFast。1,024 fd・64 B。帯はIQR。</p>

<!--
目安55秒。AとBは別の測定で、同一の縦軸や速度比較へ混ぜない。左はwait APIとイベント索引取得の時間/回（µs）。pollのrevents走査とepollのイベント配列走査を含み、データ受信や送信は含めない。全イベント容量Nでmaxevents切り詰めはない。固定Ready集合を繰り返す合成負荷で、新規通信のイベントではない。
右は同一スレッドのProducerが送信を始めてから、Consumerの全受信・内容照合が終わるまでのバースト型End-to-End。受信区間だけの初回系列も別途保存し、取得コストを分解して確認した。WebサーバやProducerとConsumerの同時実行性能ではない。
1024 fd/64 B：Aの約1%（10/1024）でpoll42.189µs、epoll0.231µs、100%で42.558µs対16.460µs。Bの100%はpoll1.939M対epoll2.066M msg/s。値は各方式10sampleの中央値。Ready率は整数fdに丸め、実率も記録。CPU affinity未固定、VM・ホストの負荷・周波数の影響は残る。
このB条件では送信側が総時間の約47〜51%を占め、差を覆い隠す。送信と受信の区間を別々に保存することでAPI取得コストと混同しない。全体の本測定はA/受信区間の初回1280+再測定480、送信込みBの640+再測定240+逆転条件の再確認40。別seedの4096fd/100%/1KiBで小さなpoll優位が出たため次のAdaptive評価へ進んだ。

グラフはbenchmarks/poll-epoll/analyze.pyから再生成。raw.jsonl、summary.csv、environment.json、analysis.jsonが一次の実測記録。straceを付けた時間は含めない。
benchmarks/poll-epoll/README.md / results/fixed / results/replication
https://man7.org/linux/man-pages/man2/poll.2.html
https://man7.org/linux/man-pages/man7/epoll.7.html
-->

---

<div class="eyebrow">10 / ADAPTIVE?</div>

# 動的に切り替えれば速くなる？

<div class="columns benchmark-adaptive">
<div>
<img class="adaptive-chart" src="/benchmarks/D-adaptive.svg" alt="動的負荷の中央値。poll0.312M、epoll1.076M、Adaptive1.074M msg/s。各10回。" />
</div>
<div>

### 高Ready率で小さな逆転はあった
4,096 fd・全Ready・1 KiBでは、<br>pollが約2%有利な系列を確認。

### ただし、Adaptiveの改善は未確認
切り替えは中央値<strong>2回・計2.13 ms</strong>。<br>固定epollとほぼ同じ受信完了速度だった。

</div>
</div>

<div class="takeaway">逆転はあった。ただし、切り替えて速くなるとは限らない</div>
<p class="fine">4,096 fd / 1 KiB / Ready率1% → 100% → 1%、各200 ms。中央値・各10回。切り替え費用込み。</p>

<!--
目安35秒。最初の受信区間のみの系列では逆転がなかったが、送信側のReady List維持費用も含むEnd-to-Endでは、4096fd/全Ready/1KiBでpollが有利な小差が独立の2系列で出た。end-to-end-replicationはペア比中央値0.9806（poll約1.9%有利）、95%区間0.9624〜0.9920。その後のcrossover-checkでも同方向を確認したため、Adaptiveの実装条件が成立したと判断した。
動的負荷は1%→100%→1%、各200ms、10本測定+warmup1。Oracleは固定方式のrun前半からPhaseごとの方式を選び後半で評価。切替費用を無視した改善余地は約0.80%。実運用アルゴリズムではない。
Adaptiveのコストモデルは別系列crossover-checkのrun1..5から作成し、動的評価結果を見てチューニングしていない。観測した完了fd数をEMA(1/4)で平滑化し、校正済みコスト差が32バースト分で切替推定時間の1.1倍を超える場合に切り替える。最低16バースト継続。単なるReady率の手製閾値ではない。追加pollを呼んでReady率推定する処理はない。
切替は全受信済みの境界でepollをcloseし、必要時に全fdを再登録する。poll期間も裏でepollを登録し続けてProducerに費用を払わせる不公平を避けた。切替実時間、推定・判定費用は総時間に含む。開始時の初期化は別途記録し、それを含めた速度もsummary.csvに保存。全sampleで送受信・各fdの整合性が通ったが、任意の同時到着がある本番環境の切替の証明ではない。
結果はpoll0.3115M、epoll1.0763M、Adaptive1.0739M msg/s。切替回数中央値2、切替時間中央値2.130ms。Adaptive/epollのペア比改善率中央値-0.40%、bootstrap95%区間-1.61〜+2.48%。改善も悪化も断定できず、今回の方式で改善は確認できなかった。
benchmarks/poll-epoll/results/adaptive/model.json / analysis.json / raw.jsonl
benchmarks/poll-epoll/results/crossover-check / end-to-end-replication
-->

---

<div class="eyebrow">11 / IO_URING</div>

# io_uringは、I/Oを依頼して完了を受け取る

<div class="ring-flow">
<div v-click="1" class="ring-stage"><small>APPLICATION</small><strong class="ref-operation">read(fd) を記述</strong><span>SQE：依頼の1件分</span></div>
<div class="diagram-arrow">→</div>
<div v-click="2" class="ring-stage"><small>SUBMISSION QUEUE</small><strong class="ref-operation">SQ：依頼のキュー</strong><span>SQEを投入する</span></div>
<div class="diagram-arrow">→</div>
<div v-click="3" class="ring-stage kernel-stage"><small>KERNEL</small><strong>LinuxがI/Oを処理</strong><span>完了結果をCQへ</span></div>
</div>
<div class="ring-return" v-click="4"><span>Applicationが結果を取得</span><span class="diagram-arrow">←</span><strong class="ref-result">CQE：res = 128 byte</strong><span class="diagram-arrow">←</span><span class="ref-result">CQ：完了のキュー</span></div>

<div class="columns compact term-defs"><div><span class="ref-operation">SQ</span> = Submission Queue<br><span class="ref-operation">SQE</span> = Submission Queue Entry</div><div><span class="ref-result">CQ</span> = Completion Queue<br><span class="ref-result">CQE</span> = Completion Queue Entry</div></div>

<div class="takeaway">「読めそうか？」を聞く代わりに、readの結果を受け取れる</div>

<!--
目安80秒。4クリックで1つずつ説明。1: readの依頼をSQEに記述。2: SQへ投入しsubmit。3: kernelが処理。4: CQEを読み取って結果を得る。
io_uringはLinux5.1で導入された比較的新しい非同期I/Oインターフェース。SQ/CQはユーザー空間とカーネルの共有リング。SQE/CQEはそれぞれのエントリ。resは成功時にbyte数等、失敗時は負のerrnoを返す。128は図解用の値であり、追加資料snippets/io_uring_read.zigでも/dev/zeroから128byteの読み込みを実測した。
user_dataで依頼と完了を対応付ける。完了順は投入順と同じとは限らない。read用バッファは操作完了まで有効に保つ。
通常のread1件の例。multishotやCQE抑制もあるのでSQEとCQEが常に1対1とは言わない。Zigのstd.os.linux.IoUringはこの直接操作用ラッパーで、後のstd.Io.Uringとは別の層。
https://man7.org/linux/man-pages/man7/io_uring.7.html
https://man7.org/linux/man-pages/man2/io_uring_setup.2.html
Zig0.17.0同梱: lib/std/os/linux/IoUring.zig
-->

---

<div class="eyebrow">12 / WHY IT CAN HELP</div>

# なぜio_uringは速くなり得る？

<div class="reason-list">
<div v-click><b>まとめて依頼</b><p>複数のI/Oをバッチで投入し、同時に進行させる。</p></div>
<div v-click><b>共有リングで受け渡し</b><p>依頼・結果の受け渡しを効率化。syscall境界をまたぐ回数を減らせる。</p></div>
<div v-click><b>繰り返しの準備を減らす</b><p>registered buffers：バッファを事前登録し、操作ごとの準備を削減。</p></div>
</div>

<div class="takeaway">I/Oの待ち時間と、1件ごとの手間をまとめて減らす余地がある</div>

<p class="fine">syscallが不要になるわけではない。効果は操作・設定・ワークロードに依存する。</p>

<!--
目安45秒。共有リングはI/Oデータすべてを常にzero-copyで渡すという意味ではない。
setup / mmap / register / enterなどのsyscallを使う。submitや完了待機をまとめると、1件ずつ要求・待機する場合の境界通過や待機/再開に伴うcontext switchを減らせる可能性がある。ただしsyscallの呼び出しとschedulerのcontext switchは同義ではない。
SQPOLLなどでsubmit syscallを減らせるが、追加threadやCPUコストがあり無条件な利益ではない。registered buffersはメモリを事前登録しpin/mapping等の処理を償却する最適化で、対応操作やmemlock制限がある。すべてのプログラムで有効になるわけではない。
PostgreSQLの最大3倍をここの仕組みだけの効果と結び付けて断定しない。FUSE等の追加ベンチマークは条件の紹介に時間が必要なので本編には追加しない。
https://man7.org/linux/man-pages/man7/io_uring.7.html
https://man7.org/linux/man-pages/man2/io_uring_register.2.html
https://kernel.org/doc/html/latest/filesystems/fuse/fuse-io-uring.html
-->

---

<div class="eyebrow">13 / EPOLL</div>

# epollは「I/Oできる状態」を教える

<div class="flow horizontal epoll-flow"><div><strong>epoll_wait()</strong><small>登録したfdをまとめて待つ</small></div><span class="connector">→</span><div v-click><strong class="ref-fd">fd 5 がread可能</strong><small>準備完了の通知</small></div><span class="connector">→</span><div v-click><strong class="ref-operation">read(fd5)</strong><small>アプリがI/Oを実行</small></div><span class="connector">→</span><div v-click><strong class="ref-result">データを取得</strong><small>戻り値を確認</small></div></div>

<p class="big-statement smaller">Reactorモデル：<br><strong>準備完了を知ってから、自分でI/Oする。</strong></p>

<div class="takeaway">epoll自身がreadを代行するわけではない</div>

<p class="fine">Edge-triggeredではnon-blockingで処理し、EAGAINで再待機。EOF・エラーも判定する。</p>

<!--
目安35秒。「io_uringの操作完了に対して、epollは準備完了を知らせる」と戻って比較する。
readinessの通知を受けても返り値の確認は必要。readinessは要求byte数すべてを読める保証ではない。通常はnon-blockingでEAGAINまで読む。EOF/エラーも扱う。Level-triggeredとEdge-triggeredの詳しい解説は本編では省く。
Reactorはパターン名。epollは多数の接続を待つ成熟した方式であり、古いから劣るという話ではない。regular fileのI/O待機を一般的にepollで同じように扱えるとは説明しない。
https://man7.org/linux/man-pages/man7/epoll.7.html
-->

---

<div class="eyebrow">14 / READINESS vs COMPLETION</div>

# 「準備完了」と「操作完了」の違い

<div class="columns compare-flow">
<div>

### epoll / Reactor
<div class="flow vertical"><div>準備完了を待つ</div><span>↓</span><div v-click="1" class="ref-operation">アプリがreadを実行</div><span>↓</span><div v-click="2" class="ref-result">結果を受け取る</div></div>
<p class="fine">socketの待機で広く利用。<br>通知後のI/Oと再試行はアプリが管理。</p>

</div>
<div>

### io_uring / Proactor的な利用
<div class="flow vertical"><div class="ref-operation">readを登録する</div><span>↓</span><div v-click="1">操作の完了を待つ</div><span>↓</span><div v-click="2" class="ref-result">結果を受け取る</div></div>
<p class="fine">操作の投入と完了をまとめて扱える。<br>完了までのバッファ寿命などの管理が必要。</p>

</div>
</div>

<div class="takeaway">同じreadでも、アプリとOSの役割の分け方が違う</div>

<p class="fine">io_uringにもpollによるreadiness通知がある。完全に排他的なモデルではない。</p>

<!--
目安40秒。同じreadの流れを左右で2クリックずつ対比する。Proactorは完了通知を使う設計モデルとして簡潔に触れる。
epollは成熟したsocket readiness待機の仕組み。通知後に自分で操作するのでアプリの制御を保ちやすい一方、EAGAINやpartial I/Oなどのループはruntime/アプリ側が管理する。
io_uringはファイルも含む各種操作を完了として受け取れるが、要求識別、バッファ寿命、キャンセルとの競合などの設計が必要。io_uringにもPOLL_ADD等があり、内部でpollやworkerを使う経路もある。どちらか一方しか利用できないという比較ではない。
性能で必ずどちらが勝つという主張をしない。利用する操作と実装の複雑さ、既存runtimeとの適合で選ぶ。
https://man7.org/linux/man-pages/man7/epoll.7.html
https://man7.org/linux/man-pages/man7/io_uring.7.html
https://man7.org/linux/man-pages/man2/io_uring_enter.2.html
-->

---

<div class="eyebrow">15 / I/O INTERFACE</div>

# Zigのstd.Ioで、I/O実装を分離する

<div class="columns io-interface">
<div>

```zig
fn app(io: std.Io) !void {
    try std.Io.File.stdout().writeStreamingAll(
        io,
        "Hello, World!\n",
    );
}
```

<span class="ref-fd">io</span>を受け取り、<span class="ref-buffer">同じ文字列</span>を出力する。

</div>
<div>
<div class="flow vertical compact-flow"><div>同じ app(io)</div><span>↓</span><div class="ref-fd">std.Io</div></div>
<div class="branch-line"></div>
<div class="backend-pair"><div><strong>Threaded</strong><small>通常のwrite系syscall</small></div><div><strong>Evented</strong><small>LinuxではUringを選ぶ</small></div></div>
<p class="fine">切り替えるのは呼び出し側の初期化。<br>Eventedは実験的で、0.17.0ではビルドに制約あり。</p>
</div>
</div>

<div class="takeaway">アプリの処理を保ったまま、I/Oの実装を選ぶ設計</div>
<p class="fine">io_uringや実装の差し替えはZig固有ではない。今回は標準ライブラリの設計を見る。</p>

<!--
目安35秒。epollとio_uringの比較から「操作と実行の仕組みを分ける」話へ。
同じapp()を両方の分岐から呼ぶsnippets/io_backend_demo.zigを示す。snippets/build.zigの-Dbackendでコンパイル時に選ぶ。ThreadedはIo.Threaded.init(init.gpa, .{})、Eventedはundefinedの変数にtry backend.init(init.gpa, .{})を呼び、どちらもdefer deinit、app(backend.io())。
0.17.0同梱Io.zigのEventedはfiber.supportedとOSで選択する型。LinuxではUring。この図は設計と選択関係であり、両方の実行成功を示す図ではない。Eventedの実際のコンパイル障害は次のページで示す。
DIやインターフェースによる実装分離もio_uring利用も他言語で可能。Zigの性能優位性の根拠にはしない。このデモで性能比較は行わない。
https://ziglang.org/download/0.17.0/release-notes.html
https://ziglang.org/documentation/0.17.0/std/
0.17.0同梱 lib/std/Io.zig、Io/Threaded.zig、Io/Uring.zig
-->

---

<div class="eyebrow">16 / OBSERVED RESULT</div>

# 同じコードで、syscallは変わる？

<div class="columns backend-traces">
<div>

### Threaded：実行・strace確認済み

```text
writev(1,
  [{iov_base="Hello, World!\n",
    iov_len=14}], 1) = 14
```

<span class="ref-operation">writev</span>で<span class="ref-fd">stdout（fd 1）</span>へ<br><span class="ref-result">14 byte</span>を出力。

</div>
<div>

### Evented：ビルド時に停止

```text
error: no field named
'processReplacePath'
in struct 'Io.VTable'
```

0.17.0の標準ライブラリ内の不整合。<br><strong>io_uringのsyscallは未観測。</strong>

</div>
</div>

<div class="takeaway">差し替える設計は確認できた。両者のsyscall比較は未完了</div>
<p class="fine">Linux aarch64 / Zig 0.17.0・標準ライブラリ未改変。straceはPIDを除き折り返し。性能比較なし。</p>

<!--
目安40秒。両方で同じ出力、Eventedでio_uring_setup/enterという結果を期待したが、実測はThreadedのみ成功。両方が動いたように説明しない。
実行環境はorb -m zig-syscall-lab、Linux 7.0.14 aarch64、Zig 0.17.0。Threaded stdoutはHello, World!と改行。straceはwritev(1, [{iov_base="Hello, World!\n", iov_len=14}], 1) = 14。スライドではPIDを除き、表示上折り返した。writevは複数のバッファを扱えるwrite系syscall。
EventedはIo/Uring.zig:759のVTable初期化で、Io.VTableに存在しないprocessReplacePathを指定するためコンパイル失敗。公式ソースアーカイブとローカル・VMの配布ライブラリの一致を確認。標準ライブラリへのパッチや別バージョンへの置換を行った実行結果としては提示しない。
Io/Uring.zigにはprocessSpawnPathやinheritParentDir/Fileとの不整合もある。1行削除するだけで動くとは説明しない。
初期化の実装はリングを作るが、それはソースを読んだ知識でありstraceで観測した結果ではない。修正版で両方の実行とsetup/enterの観測が必要。独立の低レベルIoUringサンプルの実測をこのEventedの実測に流用しない。
再実行：npm run check:backends。完全記録 docs/validation-backends.json、手順 snippets/README.md。
https://ziglang.org/documentation/0.17.0/std/
0.17.0同梱 lib/std/Io/Uring.zig:759 / lib/std/Io.zig:51
-->

---

<div class="eyebrow">17 / BACKEND SUPPORT</div>

# std.Ioにも、実装ごとの対応差がある

<div class="columns io-interface">
<div>

### Threaded
既定のstd.process.Initが渡す実装。<br>今回の出力処理は実行できた。

### Evented / Uring
Linux向けの実験的な実装。<br>0.17.0はビルド不整合があり、<br>listen / accept / connect等にも未対応。

</div>
<div>
<div class="flow vertical compact-flow"><div>Zig Application</div><span>↓</span><div><strong class="ref-fd">std.Io</strong></div></div>
<div class="branch-line"></div>
<div class="backend-pair"><div><strong>Threaded</strong><small>thread中心の実装</small></div><div><strong>Evented</strong><small>LinuxではUringを選ぶ</small></div></div>
</div>
</div>

<div class="takeaway">インターフェースが共通でも、対応状況は確かめる</div>
<p class="fine">Futureで関数呼び出しも扱えるが、並行実行の可否やキャンセルの動作も実装に依存する。</p>

<!--
目安20秒。0.17.0のIo.EventedはOSとfiber.supportedで型を選び、LinuxではIo.Uring、macOSではIo.Dispatch。Threaded / Evented / Uringを独立した3実装として描かない。非対応targetではEventedがvoidになる。
UringのVTable不整合に加え、netListenIp/netAccept/netConnectIpはUnavailable経由でNetworkDownを返す。process操作等にもTODO panicが残る。完成度や全APIの同等性を保証しない。
Futureを作るio.asyncは逐次実行へfallback可能で、必ず並行実行する保証はない。io.concurrentは並行実行できなければConcurrencyUnavailable。cancelは停止要求であって強制停止ではない。
std.os.linux.IoUringという低レベルAPIとstd.Io.Uringは別。低レベルサンプルの成功はEventedバックエンドの成功を意味しない。
https://ziglang.org/documentation/0.17.0/std/
https://ziglang.org/download/0.17.0/release-notes.html
0.17.0同梱 lib/std/Io.zig / Io/Threaded.zig / Io/Uring.zig
-->

---

<div class="eyebrow">18 / DEPENDENCY INJECTION</div>

# I/Oを差し替えられると、何がうれしい？

<div class="columns di-diagrams">
<div><h3>Webでよく見るDI</h3><div class="flow vertical compact-flow"><div>Web Application</div><span>↓</span><div>Database Interface</div></div><div class="branch-line"></div><div class="backend-pair"><div>Postgres</div><div>Mock</div></div></div>
<div><h3>ZigのI/Oインターフェース</h3><div class="flow vertical compact-flow"><div>Zig Application</div><span>↓</span><div class="ref-fd">std.Io</div></div><div class="branch-line"></div><div class="backend-pair"><div>Threaded</div><div>failing</div></div></div>
</div>

<div class="experiment-result"><strong>同じapp(io)を実行</strong><span>Threaded：<b class="ref-result">helloを出力</b></span><span>failing：<b class="ref-result">error.InputOutput</b></span></div>

<div class="takeaway">実装への依存を局所化し、同じ処理の成功・失敗を確かめられる</div>

<p class="fine">実測はこの小さな出力処理のみ。failingは汎用のMockや全動作を再現する実装ではない。</p>

<!--
目安35秒。DIはdependency injection、依存性注入。呼び出し側が具体実装を渡す設計の類比であり、DBインターフェースとstd.Ioが同じAPIという意味ではない。
Zig0.17.0は標準でstd.Io.failingを提供する。全操作が同じ失敗を返す汎用Mockという意味ではなく、asyncを直接実行するなど操作ごとの振る舞いがある。std.testing.ioもテストから使える。
snippets/io_injection.zigが、io_basic.zigと同じapp関数をThreadedとstd.Io.failingへ渡す。Linux実測はstdoutにhello、stderrにThreaded: success / failing: InputOutput。この1操作で切り替えと失敗を確かめた。
これでio_uringの内部処理や性能が検証できたとは言わない。0.17に標準のepollバックエンドが揃い、同じコードの差し替えだけでepoll vs io_uringのベンチマークができるとも言わない。
キャンセルは停止要求であり強制停止ではない。実装ごとの対応を確認する必要がある。既存tests/future_contract.zigは逐次fallback、ConcurrencyUnavailable、結果のエラー共用体を確認するが、Uringの非同期キャンセルの実証ではない。
https://ziglang.org/documentation/0.17.0/std/
0.17.0同梱: lib/std/Io.zig のfailing / Future、lib/std/testing.zig のio
-->

---

<div class="eyebrow">19 / LIMITS</div>

# io_uringなら、何でも速い？

<p class="big-statement smaller"><strong>速くなる条件がある。</strong></p>

<div class="columns limits">
<div>

### 手間が上回ることもある
少量のI/Oでは、リングや要求管理の<br>オーバーヘッドを回収できない場合がある。

### ボトルネックはどこか
CPU側の手間を減らしても、ストレージや<br>ネットワークの限界はそのまま残る。

</div>
<div>

### 使う側の設計も変わる
並行する要求、バッファの寿命、<br>キャンセルを扱う必要がある。

### 環境によって違う
Linuxのバージョン、対応操作、<br>runtimeの実装を確かめる。

</div>
</div>

<div class="takeaway">ワークロードを決めて測る。epollが合う場面もある</div>

<!--
目安45秒。「調べてみると、置き換えれば全部速くなる話ではなかった」。少量I/Oのコストや物理ボトルネックは設計上の考察で、今回の性能実測結果としては示さない。
実際に複数I/Oを並行させなければ利点を得にくい。登録、submit、completionの取り回し、SQPOLLのCPUコストなどがあり、単純な1件ずつのI/Oは有利とは限らない。
実例としてPostgreSQL18のAIO改善とlibuvの既定方式のrollbackを口頭で対比できる。ただし後者を「遅かったから戻した」と断定しない。公式fsドキュメントはrollbackの事実を示すもので、原因や公平な性能比較を示していない。
条件付きの公平なepoll対io_uringベンチマークは今回行っていない。新しいマイクロベンチマーク値を創作しない。
https://docs.libuv.org/en/v1.x/fs.html
https://www.postgresql.org/about/news/postgresql-18-released-3142/
https://man7.org/linux/man-pages/man7/io_uring.7.html
https://man7.org/linux/man-pages/man2/io_uring_register.2.html
-->

---

<div class="eyebrow">20 / SECURITY & OPERATIONS</div>

# 使いたくても使えないことがある

<div class="flow horizontal security-flow"><div>Application</div><span class="connector">→</span><div class="ref-operation">io_uring_setup()</div><span class="connector">→</span><div>seccomp<br><small>syscallの許可・拒否</small></div><span class="connector">→</span><div class="ref-result">EPERM<br><small>許可されない例</small></div></div>

<div class="columns compact">
<div>

### Dockerの既定プロファイルの例
公式資料ではio_uring関連syscallをブロック。<br>実際の挙動はEngine・適用プロファイルで変わる。

</div>
<div>

### 別のI/O方式を用意する
初期化の可否を確認し、<br>thread poolなどへのfallbackを検討する。

</div>
</div>

<div class="takeaway">性能だけでなく、実行環境のポリシーも採用条件になる</div>

<p class="fine">2026-10-18時点のDocker公式資料。EPERMの原因はseccompだけとは限らない。</p>

<!--
目安35秒。seccompはsyscallをフィルタするLinux機構。現在のDocker公式ドキュメントはdefault profileでio_uring_setup/enter/registerをブロックする一覧を掲載し、セキュリティ問題を理由として説明する。
図は拒否プロファイルが適用された場合の例。すべてのDockerバージョンやカスタムプロファイルが必ず拒否するという意味ではない。システム側のio_uring_disabledや権限などでもEPERMになり得る。環境を確認する。
今回のOrbStack Linuxでは直接io_uring_readを実行できた。Dockerコンテナ内の拒否は今回実測していない。
運用上は利用可否の検出とfallbackを検討する。libuvのthreadpool fallback、PostgreSQLのworker選択はその考え方の例。std.Io.Uringが全操作について自動的にThreadedへfallbackする保証はない。
この発表ではseccomp無効化やprivileged実行を推奨しない。必要な機能とポリシーの両立を運用側と確認する。
https://docs.docker.com/engine/security/seccomp/
https://github.com/moby/profiles/blob/main/seccomp/default.json
https://man7.org/linux/man-pages/man2/io_uring_setup.2.html
https://docs.libuv.org/en/v1.x/fs.html
-->

---

<div class="eyebrow">21 / WHAT I LEARNED</div>

# 非同期I/Oの裏側を覗いてみた

<div class="closing-list">
<div><b>01</b><span>async/awaitの下には、OSのI/O機構がある。</span></div>
<div><b>02</b><span>io_uringは、I/Oの依頼と完了を効率よく扱うLinuxの仕組み。</span></div>
<div><b>03</b><span>epollとio_uringには、異なる設計と得意分野がある。</span></div>
<div><b>04</b><span>Zigでは、syscallの観察もstd.Ioによる抽象化もできる。</span></div>
<div><b>05</b><span>性能・互換性・セキュリティを確かめて使う。</span></div>
</div>

<div class="takeaway closing-message">普段の非同期処理。その少し下に、Linuxの面白い仕組みがある。</div>

<!--
目安40秒。調べた順に発見を振り返り、冒頭の「いつも使うawaitの裏側」という問いに戻る。
Zigは観察の道具であって今回の話をZigだけに閉じない。runtimeのコードやstraceを眺めることも次の入口になる。
高性能かどうかは自分のワークロードで測る。今回の結果はAPIと動作の確認であり、性能改善の実証ではない。
最後は「普段何気なく使っている非同期処理。その少し下を覗くと、Linuxの面白い仕組みが見えてくる」と口頭で締める。
-->

---

<div class="eyebrow">22 / REFERENCES</div>

# 参考資料

<div class="columns reference-grid">
<div>

### Zig / runtime
- [Zig 0.17.0 release notes](https://ziglang.org/download/0.17.0/release-notes.html) / [標準ライブラリ](https://ziglang.org/documentation/0.17.0/std/)
- [Zig overview](https://ziglang.org/learn/overview/)
- [libuv: design](https://docs.libuv.org/en/v1.x/design.html) / [filesystem](https://docs.libuv.org/en/v1.x/fs.html)
- [Python: event loop](https://docs.python.org/3/library/asyncio-eventloop.html#event-loop-implementations)

### Linux
- [syscalls(2)](https://man7.org/linux/man-pages/man2/syscalls.2.html) / [read(2)](https://man7.org/linux/man-pages/man2/read.2.html) / [write(2)](https://man7.org/linux/man-pages/man2/write.2.html)
- [poll(2)](https://man7.org/linux/man-pages/man2/poll.2.html) / [epoll_wait(2)](https://man7.org/linux/man-pages/man2/epoll_wait.2.html)
- [epoll(7)](https://man7.org/linux/man-pages/man7/epoll.7.html) / [io_uring(7)](https://man7.org/linux/man-pages/man7/io_uring.7.html)
- [io_uring_register(2)](https://man7.org/linux/man-pages/man2/io_uring_register.2.html)

</div>
<div>

### 採用事例 / 運用
- [PostgreSQL 18 release](https://www.postgresql.org/about/news/postgresql-18-released-3142/)
- [PostgreSQL 18: io_method](https://www.postgresql.org/docs/18/runtime-config-resource.html#GUC-IO-METHOD)
- [Dragonfly: architecture](https://www.dragonflydb.io/guides/redis-and-dragonfly-architecture-comparison)
- [Dragonfly: SSD tiering](https://www.dragonflydb.io/blog/dragonfly-ssd-data-tiering-community-announcement)
- [Docker: seccomp](https://docs.docker.com/engine/security/seccomp/)
- [Kernel: FUSE-over-io_uring](https://kernel.org/doc/html/latest/filesystems/fuse/fuse-io-uring.html)

</div>
</div>

<p class="fine">確認日：2026-10-18。補足・各スライドの出典は発表者ノート、実行例は snippets/ に記載。</p>

<!--
参考資料は発表時間に含めて読み上げない。質問時に利用する。すべて一次資料。リンクは2026-10-18に内容を確認。
ZigのIo / Future / Threaded / Uring / failingは公式0.17.0配布ソースとも照合した。公式ソースアーカイブのSHA256とローカル同梱4ファイルの一致を前回レビューで確認済み。
https://ziglang.org/download/index.json
https://ziglang.org/download/0.17.0/zig-0.17.0.tar.xz
https://man7.org/linux/man-pages/man2/open.2.html
https://man7.org/linux/man-pages/man2/io_uring_enter.2.html
https://man7.org/linux/man-pages/man2/io_uring_setup.2.html
https://github.com/moby/profiles/blob/main/seccomp/default.json
https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/await
この資料はzig_async_syscalls_lt_webfriendly.pdfの学習内容をもとに、発見を共有する15分LTとして再構成したもの。
-->
