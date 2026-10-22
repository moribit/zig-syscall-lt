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

# なぜepollは低Ready率に強い？

<p class="benchmark-scenario">1,024 fdのうち、<strong>読み取り可能なのは10 fd</strong>なら？</p>

<div class="benchmark-model">
<h3 class="bench-poll">poll：毎回fd集合を走査する</h3>
<div class="flow horizontal"><div>1,024 fdの配列</div><span class="connector">→</span><div>全体を確認する</div><span class="connector">→</span><div>Readyな10 fd</div></div>
<h3 class="bench-epoll">epoll：監視対象を先に登録する</h3>
<div class="flow horizontal"><div>1,024 fdを事前登録</div><span class="connector">→</span><div>通知でReady Listへ</div><span class="connector">→</span><div>10 fdを確認・取得</div></div>
</div>

<p class="kernel-notification">Wait Queue（通知の待ち先） → <code>ep_poll_callback()</code> → Ready List</p>

<div class="takeaway">epollは通知を利用し、待機のたびに全fdを確認する仕事を減らす</div>
<p class="fine">Ready率 = 読み取り可能な監視fd数 / 監視fd総数。どちらも受信処理はアプリ側で行う。</p>

<!--
目安35秒。Non-blockingで全部を何度もreadする代わりに、読み取り可能なfdを待つ仕組みを使う。pollとepollはreadiness通知の方式。epollに登録する費用もあり、常に速いとは限らない、という問いから実験へ。
1024 fdのうち10 fdは0.9765625%。図は取得経路を簡略化した概念図で、epollが全処理O(1)という意味ではない。取得するReadyイベント数が増えればコピー・処理費用も増える。
今回の実験はnon-blocking Unix Domain Socketのsocketpair、Consumer 1スレッド。epollはLevel-triggeredで、読み取り可能な状態なら再通知される。
https://man7.org/linux/man-pages/man2/poll.2.html
https://man7.org/linux/man-pages/man7/epoll.7.html
https://man7.org/linux/man-pages/man2/epoll_wait.2.html
追加監査：上流stable v7.0.14 fs/eventpoll.cのrbr（Interest List索引）、rdllist（Ready List）、ep_insert/ep_ptable_queue_proc、ep_poll_callback、ep_send_eventsを確認。登録時に対象fdのWait Queueへcallbackを登録し、通知で候補をReady Listへ追加。待機時は候補を再確認・コピーし、LTでは再配置する。すべての処理がO(1)ではない。Wait QueueはCPUを使って回り続けるループの意味ではない。
測定版は7.0.14-orbstack-00380-ga7e0a2dc9535。独自patchの公開ソースを取得できず、同じベース版の上流実装を参照した。完全一致は未確認。
https://github.com/gregkh/linux/blob/v7.0.14/fs/eventpoll.c#L1267
https://github.com/gregkh/linux/blob/v7.0.14/fs/select.c#L872
benchmarks/poll-epoll/ANALYSIS.md
-->

---

<div class="eyebrow">09 / MEASURED COST</div>

# Kerrisk氏の測定を、CとZigで追試

<img class="audit-measured" src="/benchmarks/kerrisk-density.svg" alt="過去の表と現在のC/Zig再構成を別パネルで比較。1,000 fd、100万回。過去の高Ready率ではpollが優位。現在の結果は保存済み実測から生成。" />

<div class="benchmark-numbers"><span>過去は高Ready率で<b class="bench-poll">poll優位</b>。今回の条件ではepoll優位。</span><small>元Cは未入手。公開仕様から再構成し、過去と現在を別の実験として比較した。</small></div>

<div class="takeaway">I/O APIの性能は、何をどこまで測るかによっても変わる</div>
<p class="fine">今回：1,000 pipe fd・低位連続・100万回×各3回。timeout=-1、容量N、走査なしは仮定。OrbStack / Zig 0.17.0。</p>

<!--
目安55秒。Kerrisk氏の講義で「高Ready率ではpollが逆転した」表を見つけ、現在のLinuxで同じような現象が出るかを調べた。過去の参考値・現在のC再構成・現在のZig再構成を別パネルに分け、異なる環境/未知の条件を同一系列の線で結ばない。selectも本実験には含むが、LTの図は主題のpoll/epollだけに絞る。
元のaltio/altio_speed.cは公式TLPIのdist/book版20260523や公開候補で入手できなかった。講義の仕様に基づく独立したCとZigの再構成であり、オリジナルの無改変実行ではない。pipeや低位連続fdを使う考え方は確認したが、表が実際に使ったfd種、timeout、maxevents、イベント走査等の詳細は未確認。主比較のpipe、timeout=-1、容量N、走査なしには仮定を含む。図の未知条件の注意を省略しない。
図はReady検出のみ、データは読まず、1 byteを入れたReady状態を繰り返し取得する。新規I/Oメッセージを100万回受信した実験ではない。CはGCC -O2、Zig0.17.0 ReleaseFast、Linux7.0.14-orbstack aarch64、M2 MacBook Air上のFedora VM、CPU2固定。VM affinityは物理CPU専有を保証しない。初期登録・Ready生成・事前集合検証は計時外。
全Ready/1000fd/100万回の秒数、各3sampleの中央値と名目95%bootstrap区間：c/poll 27.241s [27.232,27.312]; c/epoll 10.703s [10.437,10.803]; zig/poll 27.303s [27.150,27.309]; zig/epoll 10.698s [10.442,10.748]。原典はpoll12.7s/epoll47.3s。元の測定日時・CPU・kernel・sample数は不明。n=3の区間は粗く、確認的有意性の証拠にはしない。
Ready10/20/50/100%とN100/1000、N1/10/100/1000の中間1Ready、K0/1/5/10のDEL+ADDを全条件保存。C/ZigのReady集合・fd範囲・件数は一致し、条件を揃えた比較だがラッパーや最適化が完全に同じではない。言語性能の優劣と結論しない。
別対照ではpipe→socket→通常fd配置→timeout0→索引走査と一要因ずつ変えた。maxevents1/16/64/Nの単発費用と、全1000Ready fdを集める費用も分けた。返すイベントが少ない1回を、全Readyを取得する1回と同じ仕事とはしない。追加の登録/投入順対照（各5sample）では、ADD後にランダム投入した場合の返却順hashを独立に確認した。全Ready/socket/連続fdのZigは投入後ADD14.769µs、投入前ADD15.619µs/回。順序による費用差はあるが、kernel内のcache miss等の直接証拠ではなく、過去の逆転の完全な原因は未特定。原典と現在の差の完全な原因は未特定。元ソース・旧環境が不明なので、CPUやkernelの改善だけに帰属させない。
既存のN1024 socketpair Aは取得API+索引変換、送信込みBはProducer開始から内容照合までを含む別実験。既存の4096fd/全Ready/1KiBの小さなpoll優位とも、範囲・fd数・データ量が異なる。既存rawとAdaptive結果は変更していない。
https://man7.org/training/download/lusp_epoll_slides-mkerrisk-man7.org.pdf （January2026 rev d49d0b54be95、物理17/18ページ）
https://man7.org/tlpi/code/index.html
benchmarks/poll-epoll/kerrisk-reproduction/REPORT.md / SOURCES.md / results/main
benchmarks/poll-epoll/ANALYSIS.md
-->

---

<div class="eyebrow">10 / ADAPTIVE?</div>

# 動的に切り替えれば速くなる？

<img class="audit-timeline" src="/benchmarks/audit-timeline.svg" alt="別の診断runで実際に選んだバックエンド。約233msでepollからpollへ、約409msでepollへ復帰。Phase境界から遅れて切り替わった。" />

<div class="audit-phase-summary">
<div><strong>各200 ms：系列間でも小差が変動</strong><br>今回の中央値-0.19%。過去は改善未確認。<br><span class="fine">切り替えは中央値2回・計2.18 ms。</span></div>
<div><strong>高Readyが長く続くと？</strong><br>1秒：<b class="ref-result">+2.53%</b> ／ 5秒：<b class="ref-result">+4.51%</b><br><span class="fine">固定モデルのまま、改善を確認した。</span></div>
</div>

<div class="takeaway">切り替える利益が、追随の遅れや切り替え費用を上回るか？</div>
<p class="fine">4,096 fd / 1 KiB / CPU 2 / 各10回のペア比中央値。A/C各200 ms、Bのみ延長。性能測定は診断無効。</p>

<!--
目安35秒。200msの既存結果を起点に、長ければ利益を回収できるかを調べた。モデル・EMA・係数は既存のまま固定、追加データを見て調整していない。B200/1000/5000msは事前指定、A/C各200ms固定、各10回。主解析は全9warmupを先に終えてから本測定したdynamic-warmed.jsonl。初回runnerにはwarmupの並べ替え不備があり、初回dynamic.jsonlとその分析も別に保存して修正前後を比較した。
Adaptive/固定epollの完了速度改善率のペア中央値、95%percentile bootstrap区間（10000回）、3条件の正確符号検定Holm補正：200ms：-0.19% [-2.25〜+2.25%], Holm p=0.75391 / 1000ms：+2.53% [+1.75〜+3.57%], Holm p=0.042969 / 5000ms：+4.51% [+3.58〜+4.95%], Holm p=0.0058594。少数の同VM追試であり他環境の保証ではない。初期setupは別記、実行中の切替費用は含む。
200msのPhase別速度中央値（M msg/s）：poll A 0.124 / B 0.660 / C 0.124; epoll A 1.298 / B 0.665 / C 1.298; adaptive A 1.297 / B 0.684 / C 1.273。Phase中央値は足し算できないため、同一run/seedごとの速度差を時間比とPhase速度の寄与へ分解した。全体速度差へ足し上がるのは各ペアの寄与の平均であり、中央値ではない。phase-contributions.csvには過去と追加の全ペアを保存。差の発生区間を示すものでkernel関数への因果分解ではない。全27条件の速度・CPU時間・完了バースト・切替はphase-summary.csv。
図は性能sampleと別の診断run（seed20261101、B200ms）の実測。epoll→pollはB第5バースト、実験開始232.883msで完了（実費0.463ms）。poll→epollはC第3バースト、409.258msで完了（実費1.702ms）。Phase境界と切替完了は一致しない。理想的なPhase境界切替の図を実挙動として描いていない。64バーストごとと全切替を事前確保メモリへ記録し終了後出力。診断の性能値は通常測定へ混ぜない。
切替合計中央値ms：200ms 2.183 / 1秒 2.233 / 5秒 2.223。closeと再登録は非対称だがControllerは直近費用を方向別に区別せず使う。初期見積はsetup。EMAは完了fd数を入力とし、generatorのPhaseを直接入力しない。最低16バースト継続、32バースト先までの推定利益と切替費用見積の1.1倍を比較する。
旧Oracle約0.80%は前半runで選び後半で評価した等時間近似、切替費用なし。追加は固定方式Phase中央値に時間重みを付けて推定しANALYSIS.mdに全条件掲載。別runの中央値からの記述的近似で、同一sampleの厳密な上限ではない。切替時間だけの回収見積は追随遅延・復帰損失を無視する楽観値。Oracleは将来の負荷を知る比較基準であり実運用アルゴリズムではない。
切替はバースト完全drain後、poll期間はepollをclose、復帰時は全fd再登録。全sampleで内容・byte数・メッセージ数が一致。任意の同時到着の正しさまでは証明しない。
benchmarks/poll-epoll/ANALYSIS.md
benchmarks/poll-epoll/results/audit-v2/dynamic-warmed.jsonl / diagnostics.jsonl / analysis.json / phase-summary.csv

Kerrisk再構成の登録費用：N100/R1/100万回のZigでK0 127.1ns/反復 / K1 524.7ns/反復 / K5 2046.5ns/反復 / K10 3999.3ns/反復。各反復K組のDEL+ADDを含み、1件は2syscall。既存Adaptiveの4096fd close/再生成/全ADDとは違う処理なので、単純に1件費用を4096倍して切替費用を説明しない。今回の追試のためにAdaptive実装・保存結果は変更していない。詳細はkerrisk-reproduction/REPORT.md。
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

# 同じ受信処理を、3方式で実測

<img class="audit-measured" src="/benchmarks/uring-recv-e2e.svg" alt="送信・内容検証・再投入を含む32バーストの処理速度。poll、epoll、io_uring RECVを同じ系列で各10回測定。" />

<div class="benchmark-numbers"><span>全Ready / 4,096 fd：<b class="bench-poll">poll 0.247</b> / <b class="bench-epoll">epoll 0.233</b> / <b class="ref-result">RECV 0.243</b> 百万件/秒</span><small>実機では6/32条件でRECVがepollを上回った（ペア速度比の中央値）。</small></div>

<div class="takeaway">syscallの削減と、処理全体の速さを分けて確かめる</div>
<p class="fine">実機 i7-3615QM / Linux 6.18.9 / Zig 0.17.0。1 KiB・32バースト×10回。初期化/終了は別計時。</p>

<!--
目安50秒。VMで比較した後、同じZig実装・条件・seed・順序でIntel実機へ追試した。ここに示すのは実機だけの送信・内容検証・再投入込みB。過去のVM結果とは混ぜていない。
Intel Core i7-3615QM、物理Mac mini、EndeavourOS、Linux6.18.9-arch1-2 x86_64、Zig0.17.0 ReleaseFast/native、libc/liburingなし。systemd-detect-virt=none。CPU2に固定するがSMT sibling6を専有しない。governor=schedutilで周波数・温度・他負荷は固定していない。fd上限はセッション内だけ16384。
N64/256/1024/4096、要求Ready1/10/50/100%、64/1024B、32バースト、全warmup後に各10sample。同じrun/seedを対応付け、方式順をランダム化。全32基本条件のうち6条件でRECV/epollペア速度比中央値が1を超えたが、うち3条件の区間は1を跨ぎ小差。探索後の確認的な有意差とは呼ばない。backend初期化・終了込みも6条件で中央値1超えだが、同じ条件とは限らない。
全Ready/4096fd/1024B、速度中央値：poll 0.247、epoll 0.233、RECV 0.243 Mmsg/s。RECV/epollペア比中央値1.040、記述的95%percentile bootstrap区間1.024–1.051。初期化・終了込み比は1.045、1.028–1.054。速度中央値同士の商とペア比中央値は異なる。4096fd/Ready約1%ではsteady比中央値1.021だが区間は1を跨ぎ、初期化込みでは0.945だった。処理量・接続寿命・計測範囲で変わる。
同じProducerを使い、単一スレッドで全送信後に全受信・内容検証・次回rearm/flushまでを測る。RECV側は将来のReady identityを知らず全fdへ初期要求を用意し、inactive要求はバースト間で維持する。32バーストの再投入境界は31回。最後はcancel受付と対象終端CQEまで排出し、bufferを解放する。
batch1→最大の全Ready/4096fd/1KiB対照では、E2E enter126976→31、0.209→0.243 Mmsg/s、プロセスCPU626.223→536.008ms。最大batchが常に最速ではない。CQ回収上限の変更は端数flush頻度も変え、コピー単体の費用ではない。batch64を揃えたSQ64/N対照80件も実機で追試し、区間はいずれも1を跨いだ。
POLL_ADD oneshot+recvは再武装込みの通知→排出サイクルであり、非消費LT再通知とは契約が違うため専用図へ分離。主図はRECVのB。straceは別の12実行で件数を検証し、tracer下の時間を性能値に混ぜない。x86_64のpoll/epoll_wait経路を実測した。std.os.linux.IoUringのABI実装であり、std.Io.Eventedの性能ではない。
仕組みとして共有リング、要求のまとめ投入、registered buffer等で準備を償却する余地はある。ただし今回SQPOLL/multishot/registered resourcesは使わない。共有リングは全データzero-copyを意味せず、syscallとcontext switchも同義ではない。CPUはgetrusageのプロセス時間で、kernel worker/ホスト全体のCPUとは違う。時計オーバーヘッドを含む。区間中央値を単純加算しない。
VMでは基本32条件でepollが速い中央値だったが、実機では上回る条件もあった。同時にCPU、aarch64/x86_64、kernel版、native target、SMT、周波数制御が違うため「仮想化のオーバーヘッド」だけを測ったとは言えない。別日の独立系列や継続到着/TCP/TLS/Web処理は未検証。Kerrisk/Adaptiveページは過去のVM系列のままで、この追試で実機に移したと説明しない。
benchmarks/poll-epoll/io-uring/PHYSICAL_ANALYSIS.md / results/physical-20261022
https://man7.org/linux/man-pages/man2/io_uring_enter.2.html
https://man7.org/linux/man-pages/man2/io_uring_register.2.html
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

0.17.0の標準ライブラリ内の不整合。<br><strong>Evented経由のsyscallは未観測。</strong>
<p class="fine">低レベルのstd.os.linux.IoUringは別途実行済み。<br>straceでsetup / enterの成功を確認。</p>

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
今回のRECV/POLL_ADD実測はstd.os.linux.IoUringを使い、std.Io.Eventedを使っていない。低レベルではRECVの最小実行・三方式比較・未完了要求の終了まで確認済み。Eventedのビルド失敗という結論は変更しない。
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
高性能かどうかは自分のワークロードで測る。今回はAPIの観察と合成負荷での比較。Webサーバ全体の性能改善を実証したものではない。
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
- [epoll(7)](https://man7.org/linux/man-pages/man7/epoll.7.html) / [io_uring(7)](https://man7.org/linux/man-pages/man7/io_uring.7.html) / [enter(2)](https://man7.org/linux/man-pages/man2/io_uring_enter.2.html)
- [io_uring_register(2)](https://man7.org/linux/man-pages/man2/io_uring_register.2.html)
- [Linux v7.0.14: eventpoll.c](https://github.com/gregkh/linux/blob/v7.0.14/fs/eventpoll.c)
- [Kerrisk: epoll講義](https://man7.org/training/download/lusp_epoll_slides-mkerrisk-man7.org.pdf)

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

<p class="fine">既存資料確認：2026-10-18、poll/epoll追加調査：10-19。補足と出典は発表者ノート・ANALYSIS.md。</p>

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
poll/epollの追加監査は2026-10-19。上流stable v7.0.14を参照、OrbStack独自patchの完全照合は未確認。benchmarks/poll-epoll/ANALYSIS.mdとresults/audit-v2を参照。
この資料はzig_async_syscalls_lt_webfriendly.pdfの学習内容をもとに、発見を共有する15分LTとして再構成したもの。
-->
