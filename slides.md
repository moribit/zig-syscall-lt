---
theme: default
title: Zigで覗く、Linuxの非同期I/O
info: |
  Webエンジニア向けLT。短いZigプログラムとstraceで、poll・epoll・io_uringの役割を観察する。
class: cover
layout: default
colorSchema: dark
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

<div class="cover-sub">poll・epoll・io_uring を、動かして見る</div>
<div class="cover-bottom">いつも使う async/await の、少し下へ。</div>

<!--
目安15秒。15分前後を目安に、初学者の理解を優先して説明する。発表前の手順は demos/PRESENTER.md。
口頭で「hotoさんのPython非同期処理LTを見て、待つ仕組みが気になった」と動機を話す。専用スライドにはしない。
今日は性能ではなく、カーネルに何を頼み、何が返るかを見る。OrbStackのLinuxで実演する。
-->

---

<div class="eyebrow">01 / いつもの非同期処理</div>

# async/await の下では何が起きている？

<p class="big-statement smaller">レスポンスを待つ間、<br>「データが届いた」と誰が教えてくれる？</p>

<div class="flow horizontal live-runtime">
<div>JavaScript / Python<small>async / await</small></div><span class="connector">→</span>
<div>Runtime<small>待機と処理の再開を管理</small></div><span class="connector">→</span>
<div>OSのI/O機構<small>Linuxでは epoll など</small></div>
</div>

<p class="fine">典型的なネットワークI/Oの一例。言語・runtime・操作によって経路は異なる。</p>
<div class="takeaway">その下にあるLinuxの仕組みを、直接見てみる</div>

<!--
目安35秒。awaitが直接epollを呼ぶわけではない。ファイルI/Oでthread poolを使うruntimeもある。
ここは問いだけ。ターミナルへはまだ移らない。
https://docs.libuv.org/en/v1.x/design.html
https://docs.python.org/3/library/asyncio-eventloop.html
-->

---

<div class="eyebrow">02 / 観察に使う道具</div>

# Zigとは？

<div class="columns compact">
<div><p class="big-statement smaller">Cに近い低レイヤーを扱える<br>システムプログラミング言語</p>
<p>メモリやリソースを明示的に管理する</p></div>
<div class="live-side-note"><strong>今回は std.os.linux</strong><p>libcを経由せず、Linuxの<br>システムコールを呼び出す</p></div>
</div>
<div class="live-cue"><b>ミニデモ：write</b><span class="ref-operation">write</span><span>→</span><span class="ref-buffer">hello</span><span>→</span><span class="ref-result">戻り値</span><strong>ターミナルへ ↗</strong></div>

<!--
目安65秒（writeミニデモ40秒を含む）。Zigの文法講座にはしない。raw syscallは他言語でも可能。
ターミナルへ。sh demos/run.sh 0 --source でwriteの1行を指す。sh demos/run.sh 0、次に sh demos/run.sh 0 --trace。
期待: stdout hello、戻り値6。straceの write(1, "hello\n", 6) = 6 を指す。説明ログはstderrにもwriteするので区別。
fd=1がstdoutと分かったところでスライド4へ戻る。ソース全文を表示したうえでwriteの行に注目する。
https://ziglang.org/documentation/0.17.0/
-->

---
class: api-explainer
---

<div class="eyebrow">システムコール</div>

# システムコールは、OSへの依頼

```zig
const n = linux.write(1, "hello\n", 6);
```

<div class="code-key"><span class="ref-fd">1：stdoutのfd</span><span class="ref-buffer">hello：データ</span><span class="ref-result">6 byteを依頼 → n byteを書き込んだ</span></div>
<div class="syscall-map compact-syscall">
<div class="space-label">ユーザー空間</div><div class="flow-node">Application</div>
<div class="space-label">syscall境界</div><div class="boundary"><span class="ref-operation">write ↓</span>　／　<span class="ref-result">↑ 戻り値 n</span></div>
<div class="space-label">カーネル空間</div><div class="flow-node">Linux Kernel → Terminal</div>
</div>
<div class="takeaway">Zigからlibcを経由せず、Linuxへ処理を依頼する</div>

<!--
目安45秒。直前のwriteデモと同じ呼び出し。nはraw syscallの戻り値で、正常なら書き込んだbyte数。
エラーはraw値にエンコードされ、部分書き込みもあり得る。確認処理はdemos/00-write.zig全文で示す。
普通の関数呼び出しの先でsyscall境界を越える。straceはすべての関数やメモリ操作を記録するものではない。
https://man7.org/linux/man-pages/man2/write.2.html
-->

---

<div class="eyebrow">04 / fd と待機</div>

# fdは、プロセスが持つ番号

<div class="columns compact">
<div class="live-fds"><div><b class="ref-fd">0 / 1 / 2</b><span>stdin / stdout / stderr</span></div><div><b class="ref-fd">そのほかの番号</b><span>ファイル / pipe / socket …</span></div><p class="fine">プロセスごとのfdテーブルで管理される。</p></div>
<div><h3>pipe：データの通り道</h3><div class="flow vertical compact-flow"><div>書き込み側の<span class="ref-fd">fd</span></div><span>↓ <span class="ref-buffer">hello</span></span><div>読み取り側の<span class="ref-fd">fd</span></div></div></div>
</div>
<div class="live-cue"><b>ミニデモ：blocking read</b><span>データなし</span><span>→ readが待つ →</span><span class="ref-buffer">到着後にhello</span><strong>ターミナルへ ↗</strong></div>

<!--
目安85秒（blockingデモ45秒を含む）。pipeには読み書きで2つのfdがある。番号は起動ごとに変わり得る。
ターミナルへ。sh demos/run.sh 1 --source は read とsendLaterだけ指す。sh demos/run.sh 1 --trace。
readの開始→1秒後にwriterがwrite→readが5を返す、を追う。sleepは送信の遅延用で、読み手自身は本物のreadでブロックしている。
待機中のスレッドがCPUを使い続けるとは説明しない。ログにhelloが出たらスライド6へ戻る。
ソース全文を表示し、readと遅延writerの役割を分ける。https://man7.org/linux/man-pages/man7/pipe.7.html
-->

---

<div class="eyebrow">待ち方を考える</div>

# データがないとき、どう待てばいい？

<div class="waiting-choices"><div><h3>blocking read</h3><p>このfdに届くまで<br><strong>スレッドが待つ</strong></p></div><div><h3>non-blocking read</h3><p>まだ届いていなければ<br><strong class="ref-result">EAGAINで戻る</strong></p></div></div>
<div class="many-fds"><span class="ref-fd">fd A ?</span><span class="ref-fd">fd B ?</span><span class="ref-fd">fd C ?</span><span>…</span><strong>何度も調べ続ける？</strong></div>
<div class="takeaway">どのfdが読み取り可能になったか、まとめて知りたい</div>

<!--
目安40秒。直前の1本のreadから、複数接続を待つ問題へ進む。
non-blockingなら即座にEAGAINで戻せるが、全fdを忙しく再確認し続けるのは避けたい。
blocking待機中のスレッドがCPUを使い続けるわけではない。EAGAINとPromise pendingを同一視しない。
次のpollは「複数fdのどれかがReadyになるまで待つ」ための道具。
-->

---
layout: api-section
apiSection: true
transition: none
---

# poll

<!--
目安5秒。話題の区切り。fd一覧を渡す方式から見てみる。 装飾・クリックなしで次へ進む。
-->

---
class: api-explainer
---

<div class="eyebrow api-poll">POLL / fd一覧を毎回渡す</div>

# pollは、fdがReadyになるのを待つ

```zig
const count = linux.poll(&fds, fds.len, 3000);
```
<div class="code-key"><span class="ref-fd">fds：監視fdの一覧</span><span class="ref-result">revents：各fdに起きたイベント</span></div>
<IoFlow mode="poll" />
<div class="takeaway">pollはデータを読まない。Readyを受け取ってからread</div>

<!--
目安50秒。コードはdemos/02-poll.zigの同じ行。fdsを毎回渡す点を図の最上段で強調する。
countはイベントのあったfd数。reventsは各要素に返るイベント。3000はtimeoutのms、速度測定ではない。
図は上から依頼→返却→read。右向きは依頼、左向きは結果、往復は依頼と結果をまとめた表現。
Readyはブロックせず進められる状態で、EOFやエラーも含み得る。データ取得はreadの段階。
https://man7.org/linux/man-pages/man2/poll.2.html
-->

---

<div class="eyebrow">LIVE DEMO / POLL</div>

# 2本のpipe、届くのは片方だけ

<div class="live-observe"><div><b>01</b><span>空のpipeでは <strong class="ref-result">EAGAIN</strong></span></div><div><b>02</b><span><strong class="ref-operation">poll</strong> が返すのは <strong class="ref-fd">Readyなfd</strong></span></div><div><b>03</b><span>そのあと <strong class="ref-operation">read</strong> すると <strong class="ref-buffer">hello</strong></span></div></div>
<div class="live-terminal">ターミナルへ ↗ <small>Readyが返っても、まだreadしていない</small></div>

<!--
目安85秒。ここでターミナルへ。sh demos/run.sh 2 --source、sh demos/run.sh 2、sh demos/run.sh 2 --trace。
ソースではfds配列・poll・readを指す。最初のtimeout=0は空の状態の確認、次のpollが本当の待機。
期待: EAGAIN → no fd ready → writerがpipe Bへ送信 → Bの読み取りfdがReady → read hello。
straceではaarch64のppollを指す。readでhelloを取得したらスライド10のepollへ進む。
ソース全文を見せ、実行ログで図と順序を対応させる。失敗時は sh demos/run.sh 2 --saved を見せ、そこで止めず次へ。
-->

---
layout: api-section
apiSection: true
transition: none
---

# epoll

<!--
目安5秒。話題の区切り。一覧を登録して保持する方式へ。 装飾・クリックなしで次へ進む。
-->

---
class: api-explainer
---

<div class="eyebrow api-epoll">EPOLL / 監視集合を保持する</div>

# epollは、初期登録と待機を分ける

```zig
const created = linux.epoll_create1(linux.EPOLL.CLOEXEC);
_ = linux.epoll_ctl(epfd, linux.EPOLL.CTL_ADD, fd, &event);
const count = linux.epoll_wait(epfd, &events, events.len, 3000);
```
<div class="excerpt-label">呼び出しの抜粋。fdの変換・戻り値の確認はデモ全文で。</div>
<IoFlow mode="epoll" />
<div class="takeaway">最初に登録し、以後は監視fd一覧を渡し直さず待つ</div>

<!--
目安60秒。demos/03-epoll.zigの3つの実在APIを抜粋。create1の戻り値createdを確認してepfdへ変換する処理は省略した。
ctl行は成功/失敗の確認を省略して表示。デモ全文にはlinux.errnoの検査がある。
図の囲み行が初期登録。instanceのfd epfdを使い、監視集合はKernel側で保持される。
waitのeventsは結果の受け取り配列で、監視fd一覧ではない。今回Level-triggered、不要なDEL/ADDはしない。
次のターミナルで登録とwaitを別々に確認する。https://man7.org/linux/man-pages/man7/epoll.7.html
-->

---

<div class="eyebrow">LIVE DEMO / EPOLL</div>

# 同じpipe、同じhelloで見てみる

<div class="live-observe"><div><b>01</b><span><strong class="ref-operation">epoll_ctl ADD</strong> で <strong class="ref-fd">2つのfd</strong>を登録</span></div><div><b>02</b><span><strong class="ref-operation">epoll_wait</strong> が <strong class="ref-fd">Readyなfd</strong>を返す</span></div><div><b>03</b><span><strong class="ref-operation">read</strong> で <strong class="ref-buffer">hello</strong>を取得</span></div></div>
<div class="live-terminal">ターミナルへ ↗ <small>登録は最初の一度。waitでReadyを受け取る</small></div>

<!--
目安90秒。ターミナルへ。sh demos/run.sh 3 --source、sh demos/run.sh 3 --trace。
ソースではcreate1・ADDのループ・wait・readの順に指す。期待: ADD2件→wait→pipe BがReady→hello。
straceのepoll_create1、epoll_ctl ADD2件、aarch64のepoll_pwaitを見る。データ取得はread。
pollと同じpipe2本・同じhello。監視一覧を毎回渡すか、登録を保持するかが違う。
read helloを見たらスライド13のio_uringへ進む。ソース全文で登録→待機→readを確認。失敗時: sh demos/run.sh 3 --saved。
-->

---
layout: api-section
apiSection: true
transition: none
---

# io_uring

<!--
目安5秒。話題の区切り。Ready通知から、操作を依頼する方式へ。 装飾・クリックなしで次へ進む。
-->

---
class: api-explainer uring-explainer
---

<div class="eyebrow api-uring">IO_URING / READ操作と完了</div>

# io_uringは、操作を頼んで完了を受け取る

```zig
_ = try ring.read(42, pipe[0], .{ .buffer = &buffer }, 0);
_ = try ring.submit();
const cqe = try ring.copy_cqe();
```
<div class="excerpt-label">std.os.linux.IoUring：低レベルラッパー。エラー処理はデモ全文で。</div>
<IoFlow mode="uring" />
<div class="takeaway">res は読み取ったbyte数、または負のerrno</div>

<!--
目安80秒。4クリック：1 READのSQEを共有SQへ準備、2 submitで通知しカーネルが処理、3 CQへ完了が返る、4 user_data=42とhelloを対応付ける。
SQ=Submission Queue、CQ=Completion Queue。SQE/CQEはそれぞれの1件。Applicationは左、Kernelは右で他方式と同じ。
SQ/CQは双方から見える共有リング。図の右列は「Kernelからも見える」側を表し、カーネル専用メモリという意味ではない。
ring.readはSQEを準備し、submitがSQを公開して今回io_uring_enterで通知する。copy_cqeはCQを進め、必要ならenterで待つ。
この3行は正常経路の呼び出し抜粋。実デモはsubmitとcopy_cqeの失敗時にpending bufferを先に解放しないようpanicする。標準ライブラリのAPIを変えているわけではない。
io_uring_setup/mmapは初期化。共有リングのメモリ操作とenter syscallを区別する。「syscallが一切不要」と言わない。
https://man7.org/linux/man-pages/man7/io_uring.7.html
-->

---

<div class="eyebrow">LIVE DEMO / IO_URING</div>

# READを投入すると、何が返る？

<div class="live-observe"><div><b>01</b><span><strong class="ref-operation">SQE</strong> に <strong class="ref-fd">pipeのfd</strong>と <strong class="ref-result">42</strong>を設定</span></div><div><b>02</b><span><strong class="ref-operation">submit</strong> して、データの到着を待つ</span></div><div><b>03</b><span><strong class="ref-operation">CQE</strong> は <strong class="ref-result">42 / 5 byte</strong>、bufferには <strong class="ref-buffer">hello</strong></span></div></div>
<div class="live-terminal">ターミナルへ ↗ <small>READを投入。CQEが来たらbufferにhello</small></div>

<!--
目安180秒。ここは3分確保。ターミナルへ。sh demos/run.sh 4 --source（60秒）、sh demos/run.sh 4（40秒）、sh demos/run.sh 4 --trace（40秒）、説明と切り替え40秒。
ソースではIoUring.init→ring.read(42, pipe[0], buffer, 0)→submit→copy_cqe→resとbufferを指す。
期待: writer到着後CQE user_data=42,res=5とhello。read操作はカーネルが実施した。copy_cqeはCQも進める。
straceのsetup/enterを見る。SQE作成とCQE回収はメモリ操作なので個別syscallとして見えない。通常のread(fd,...)がないことだけで未実行と考えない。
IoUringはZigのLinux低レベルAPI。std.Io.Eventedや過去のmultishotとは別。pipe oneshot READのみ。
buffer helloまで見たらスライド16へ戻り、ReadinessとCompletionを復習する。失敗時は10秒以内に切り替え、sh demos/run.sh 4 --saved と録画済みstraceを示す。
-->

---

<div class="eyebrow">08 / 何が通知された？</div>

# 「読み取れる」と「読み取った」の違い

<div class="columns compare-flow">
<div><h3>poll / epoll：Readiness</h3><div class="flow vertical"><div><span class="ref-fd">読める状態のfd</span>が分かる</div><span>↓</span><div>アプリが<span class="ref-operation">read</span>する</div><span>↓</span><div><span class="ref-buffer">hello</span>を取得</div></div></div>
<div><h3>io_uring READ：Completion</h3><div class="flow vertical"><div><span class="ref-operation">READ操作</span>を投入する</div><span>↓</span><div>カーネルが読み取りを処理する</div><span>↓</span><div><span class="ref-result">完了結果</span>と<span class="ref-buffer">hello</span>を取得</div></div></div>
</div>
<div class="takeaway">通知されるのは、状態か、操作の完了か</div>

<!--
目安45秒。デモの順序と対応させて振り返る。io_uringにはPOLL_ADD等もあるので完全に排他的な分類ではない。
今回比較したのはpoll/epollとIORING_OP_READの使い方。どれが速いかの証明ではない。
ターミナルから戻ったまま、以降は操作なし。
-->

---

<div class="eyebrow">3方式を、同じ順序で振り返る</div>

# 同じhelloを受け取る、3つの方法

<div class="three-methods">
<div><h3 class="api-poll">poll</h3><div class="review-step"><b>1</b><span class="ref-fd">fd一覧を渡す</span></div><span class="review-arrow">↓</span><div class="review-step"><b>2</b><span class="ref-fd">Ready通知</span></div><span class="review-arrow">↓</span><div class="review-step"><b>3</b><span><span class="ref-operation">read</span>する</span></div><div class="review-data ref-buffer">hello</div></div>
<div><h3 class="api-epoll">epoll</h3><div class="review-step"><b>1</b><span class="ref-fd">fdを事前登録</span></div><span class="review-arrow">↓</span><div class="review-step"><b>2</b><span class="ref-fd">Ready通知</span></div><span class="review-arrow">↓</span><div class="review-step"><b>3</b><span><span class="ref-operation">read</span>する</span></div><div class="review-data ref-buffer">hello</div></div>
<div><h3 class="api-uring">io_uring READ</h3><div class="review-step"><b>1</b><span><span class="ref-operation">READ</span>を依頼</span></div><span class="review-arrow">↓</span><div class="review-step"><b>2</b><span class="ref-result">CQE：操作完了</span></div><span class="review-arrow">↓</span><div class="review-step"><b>3</b><span class="ref-buffer">bufferを確認</span></div><div class="review-data ref-buffer">hello</div></div>
</div>
<div class="takeaway">一覧か登録か。Readyの通知か、操作の完了か。</div>

<!--
目安50秒。各列を同じ1→2→3→helloの順でたどる。poll/epollは監視集合の扱いが違うが、readはアプリが呼ぶ。
io_uring READは読み取り操作を先に依頼し、その完了でbufferを確認する。
これは今回使った操作の比較。io_uringにもPOLL_ADDがあるためAPI全体を完全に排他的なモデルと説明しない。
速度の優劣ではなく依頼と返却の違いを振り返る。以降ターミナル操作なし。
-->

---

<div class="eyebrow">09 / 観察して分かったこと</div>

# 短いプログラムでも、役割が見える

<div class="live-observe"><div><b>01</b><span><strong class="ref-fd">fd</strong>は、カーネルへの依頼で使う番号</span></div><div><b>02</b><span><strong class="ref-operation">poll / epoll</strong>は、複数のI/Oを待つ道具</span></div><div><b>03</b><span><strong class="ref-operation">io_uring</strong>は、操作と完了をキューでやり取りする</span></div></div>
<p class="fine">straceで見えるのはsyscallの境界。共有メモリ内の操作までは見えない。</p>

<!--
目安35秒。複雑なruntimeの中にも、今日見たような役割分担がある。
このデモは性能比較やWebサーバ全体の再現ではない。Linux機能・ポリシーによりio_uringを使えない環境もある。
図とデモから何が分かったか、聴衆の理解を確かめながら進む。詳細な制約や過去の実験はREADMEからたどれる。
-->

---

<div class="eyebrow">10 / まとめ</div>

# 非同期処理の、少し下を覗いてみた

<div class="closing-list"><div><b>01</b><span>async/await の下には、OSのI/O機構がある</span></div><div><b>02</b><span>Ready通知とCompletion通知では、依頼の仕方が違う</span></div><div><b>03</b><span>Zigとstraceで、その動きを直接確かめられる</span></div></div>
<p class="closing-message">普段何気なく使う非同期処理。<br>その少し下に、Linuxの面白い仕組みがある。</p>

<!--
目安30秒。速いAPIのランキングではなく、「何を頼んで、何が返るか」が今日の発見。
聴衆にはdemosの独立した5本を案内する。Zigに限定した仕組みではないことも一言。
-->

---

<div class="eyebrow">REFERENCES / 手元で試す</div>

# デモと参考資料

<div class="columns reference-grid">
<div><h3>短いZigプログラム</h3><ul><li><a href="https://github.com/moribit/zig-syscall-lt/tree/main/demos">github.com/moribit/zig-syscall-lt / demos</a></li><li><a href="https://ziglang.org/documentation/0.17.0/">Zig 0.17.0 Documentation</a></li></ul><h3>非同期処理の実装例</h3><ul><li><a href="https://docs.libuv.org/en/v1.x/design.html">libuv：Design overview</a></li><li><a href="https://docs.python.org/3/library/asyncio-eventloop.html">Python：Event Loop</a></li></ul></div>
<div><h3>Linux man-pages</h3><ul><li><a href="https://man7.org/linux/man-pages/man2/syscalls.2.html">syscalls(2)</a> / <a href="https://man7.org/linux/man-pages/man7/pipe.7.html">pipe(7)</a></li><li><a href="https://man7.org/linux/man-pages/man2/poll.2.html">poll(2)</a></li><li><a href="https://man7.org/linux/man-pages/man7/epoll.7.html">epoll(7)</a></li><li><a href="https://man7.org/linux/man-pages/man7/io_uring.7.html">io_uring(7)</a></li></ul></div>
</div>
<p class="fine">過去のベンチマーク・分析・旧スライドはリポジトリ内に保存。</p>

<!--
目安10秒。サンプルと当日の手順はdemos/README.mdとdemos/PRESENTER.md。
旧23枚はdocs/archive/pre-live-demo-ae3ee2a/slides.md。benchmarks以下のraw・レポート・グラフは維持。
所要時間は目安。分かりやすさを優先し、リハーサルの実測欄をPRESENTERで記入する。
-->
