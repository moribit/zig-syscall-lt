---
theme: default
title: Zigで覗く、Linuxの非同期I/O
info: |
  Webエンジニア向け15分LT。短いZigプログラムとstraceで、poll・epoll・io_uringの役割を観察する。
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

<div class="cover-sub">poll・epoll・io_uring を、動かして見る</div>
<div class="cover-bottom">いつも使う async/await の、少し下へ。</div>

<!--
目安15秒。全体14分＋操作の余白1分。発表前の手順は demos/PRESENTER.md。
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
fd=1がstdoutと分かったところでスライド4へ戻る。時間が押せばソース表示を省く。
https://ziglang.org/documentation/0.17.0/
-->

---

<div class="eyebrow">03 / システムコール</div>

# システムコールは、OSへの依頼

<div class="syscall-map">
<div class="space-label">ユーザー空間</div><div class="flow-node">Application<small>Zigのプログラム</small></div>
<div></div><div class="down-arrow ref-operation">↓ write / read</div>
<div class="space-label">境界を越える</div><div class="boundary">syscall境界</div>
<div class="space-label">カーネル空間</div><div class="flow-node">Linux Kernel<small>fdに対応するTerminal / Pipe / Socketへ処理する</small></div>
</div>
<div class="takeaway">普通の関数呼び出しの先で、カーネルに処理を頼む</div>

<!--
目安40秒。直前のstraceが境界を越えた依頼の記録。Zigのwrite関数はraw syscallを発行する薄い入口。
ユーザー空間の関数を呼ぶだけの処理と区別する。straceはすべての関数やメモリ操作を記録するものではない。
ターミナル操作なし。
https://man7.org/linux/man-pages/man2/syscalls.2.html
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
時間が押せばソース表示を省く。https://man7.org/linux/man-pages/man7/pipe.7.html
-->

---

<div class="eyebrow">05 / poll の仕組み</div>

# pollは、fdがReadyになるのを待つ

<div class="flow horizontal live-runtime">
<div>Application<small>監視する<span class="ref-fd">fd一覧</span></small></div><span class="connector">→</span>
<div><strong class="ref-operation">poll</strong><small>毎回、一覧を渡す</small></div><span class="connector">→</span>
<div>Kernel<small><span class="ref-fd">Readyなfd</span>を返す</small></div>
</div>
<div class="live-two-states"><p>non-blocking read<br><strong class="ref-result">まだデータがない → EAGAIN</strong></p><p>pollで待つ<br><strong class="ref-fd">読めるfdが分かる → readする</strong></p></div>
<div class="takeaway">Readyは「読み取りを試せる状態」。データはreadで取る</div>

<!--
目安35秒。ReadyはI/Oがブロックせず進められる状態。EOFやエラーの場合もある。
EAGAINはPromiseのpendingそのものではない。確認を高速ループする代わりにpollで待つ。
poll自体は待機中にブロックし得る。複数fdを1つの待機APIで扱う点が重要。
https://man7.org/linux/man-pages/man2/poll.2.html
-->

---

<div class="eyebrow">LIVE DEMO / POLL</div>

# 2本のpipe、届くのは片方だけ

<div class="live-observe"><div><b>01</b><span>空のpipeでは <strong class="ref-result">EAGAIN</strong></span></div><div><b>02</b><span><strong class="ref-operation">poll</strong> が返すのは <strong class="ref-fd">Readyなfd</strong></span></div><div><b>03</b><span>そのあと <strong class="ref-operation">read</strong> すると <strong class="ref-buffer">hello</strong></span></div></div>
<div class="live-terminal">ターミナルへ ↗ <small>ソース → 実行 → strace</small></div>

<!--
目安85秒。ここでターミナルへ。sh demos/run.sh 2 --source、sh demos/run.sh 2、sh demos/run.sh 2 --trace。
ソースではfds配列・poll・readを指す。最初のtimeout=0は空の状態の確認、次のpollが本当の待機。
期待: EAGAIN → no fd ready → writerがpipe Bへ送信 → Bの読み取りfdがReady → read hello。
straceではaarch64のppollを指す。readでhelloを取得したらスライド8へ戻る。
時間が押せば通常実行を省きstraceだけ。失敗時は sh demos/run.sh 2 --saved を見せ、そこで止めず次へ。
-->

---

<div class="eyebrow">06 / epoll の仕組み</div>

# epollは、監視対象を登録しておく

<div class="flow horizontal live-runtime">
<div>Application<small><span class="ref-fd">fd A / fd B</span></small></div><span class="connector">→</span>
<div><strong class="ref-operation">epoll_ctl</strong><small>監視集合を登録</small></div><span class="connector">→</span>
<div>Kernel<small>監視集合を保持</small></div>
</div>
<div class="live-registered"><span class="ref-operation">epoll_wait</span><span>→</span><span class="ref-fd">Readyなfd</span><span>→</span><span class="ref-operation">read</span><span>→</span><span class="ref-buffer">hello</span></div>
<div class="takeaway">一覧を毎回渡すpollと、登録を保持するepoll</div>

<!--
目安35秒。create1でepoll instance自体のfdができる。ctl ADDで監視集合を登録する。
epoll_waitには出力先のevent配列を渡すが、監視fd一覧を渡し直すわけではない。
今回のデモはLevel-triggered。epollはI/Oそのものを代行しない。速度の優劣には踏み込まない。
https://man7.org/linux/man-pages/man7/epoll.7.html
-->

---

<div class="eyebrow">LIVE DEMO / EPOLL</div>

# 同じpipe、同じhelloで見てみる

<div class="live-observe"><div><b>01</b><span><strong class="ref-operation">epoll_ctl ADD</strong> で <strong class="ref-fd">2つのfd</strong>を登録</span></div><div><b>02</b><span><strong class="ref-operation">epoll_wait</strong> が <strong class="ref-fd">Readyなfd</strong>を返す</span></div><div><b>03</b><span><strong class="ref-operation">read</strong> で <strong class="ref-buffer">hello</strong>を取得</span></div></div>
<div class="live-terminal">ターミナルへ ↗ <small>登録と待機を分けて見る</small></div>

<!--
目安90秒。ターミナルへ。sh demos/run.sh 3 --source、sh demos/run.sh 3 --trace。
ソースではcreate1・ADDのループ・wait・readの順に指す。期待: ADD2件→wait→pipe BがReady→hello。
straceのepoll_create1、epoll_ctl ADD2件、aarch64のepoll_pwaitを見る。データ取得はread。
pollと同じpipe2本・同じhello。監視一覧を毎回渡すか、登録を保持するかが違う。
read helloを見たらスライド10へ戻る。時間が押せばソースを省く。失敗時: sh demos/run.sh 3 --saved。
-->

---

<div class="eyebrow">07 / io_uring の仕組み</div>

# io_uringは、操作を頼んで完了を受け取る

<div class="live-rings">
<div class="live-ring-row"><div>Application</div><span>→</span><div v-click="1"><b>SQ：依頼のキュー</b><small><span class="ref-operation">SQE：READの依頼</span><br><span class="ref-result">user_data = 42</span></small></div><span v-click="2">→</span><div v-click="2">Linux Kernel</div></div>
<div class="live-ring-row"><div v-click="4">Application</div><span v-click="4">←</span><div v-click="3"><b>CQ：完了のキュー</b><small><span class="ref-operation">CQE：操作の結果</span><br><span class="ref-result">user_data = 42 / res = 5</span></small></div><span v-click="3">←</span><div v-click="3">Linux Kernel</div></div>
</div>
<div class="takeaway">今回はoneshot READ。依頼1件と、その完了を対応付ける</div>

<!--
目安55秒。4クリックでSQE→カーネル→CQE→アプリの順に見せる。
SQはSubmission Queue、CQはCompletion Queue。Entryはその中の1件。共有リングのため通常のメモリアクセスも使う。
user_dataは自分で付ける識別子、resは読み取りbyte数または負のerrno。
システムコールが不要になるわけではない。初期化setupと投入/待機enterがある。
https://man7.org/linux/man-pages/man7/io_uring.7.html
-->

---

<div class="eyebrow">LIVE DEMO / IO_URING</div>

# READを投入すると、何が返る？

<div class="live-observe"><div><b>01</b><span><strong class="ref-operation">SQE</strong> に <strong class="ref-fd">pipeのfd</strong>と <strong class="ref-result">42</strong>を設定</span></div><div><b>02</b><span><strong class="ref-operation">submit</strong> して、データの到着を待つ</span></div><div><b>03</b><span><strong class="ref-operation">CQE</strong> は <strong class="ref-result">42 / 5 byte</strong>、bufferには <strong class="ref-buffer">hello</strong></span></div></div>
<div class="live-terminal">ターミナルへ ↗ <small>SQE → submit → CQE → buffer</small></div>

<!--
目安180秒。ここは3分確保。ターミナルへ。sh demos/run.sh 4 --source（60秒）、sh demos/run.sh 4（40秒）、sh demos/run.sh 4 --trace（40秒）、説明と切り替え40秒。
ソースではIoUring.init→ring.read(42, fd, buffer, 0)→submit→copy_cqe→resとbufferを指す。
期待: writer到着後CQE user_data=42,res=5とhello。read操作はカーネルが実施した。copy_cqeはCQも進める。
straceのsetup/enterを見る。SQE作成とCQE回収はメモリ操作なので個別syscallとして見えない。通常のread(fd,...)がないことだけで未実行と考えない。
IoUringはZigのLinux低レベルAPI。std.Io.Eventedや過去のmultishotとは別。pipe oneshot READのみ。
buffer helloまで見たらスライド12へ戻る。失敗時は10秒以内に切り替え、sh demos/run.sh 4 --saved と録画済みstraceを示す。
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

<div class="eyebrow">09 / 観察して分かったこと</div>

# 短いプログラムでも、役割が見える

<div class="live-observe"><div><b>01</b><span><strong class="ref-fd">fd</strong>は、カーネルへの依頼で使う番号</span></div><div><b>02</b><span><strong class="ref-operation">poll / epoll</strong>は、複数のI/Oを待つ道具</span></div><div><b>03</b><span><strong class="ref-operation">io_uring</strong>は、操作と完了をキューでやり取りする</span></div></div>
<p class="fine">straceで見えるのはsyscallの境界。共有メモリ内の操作までは見えない。</p>

<!--
目安35秒。複雑なruntimeの中にも、今日見たような役割分担がある。
このデモは性能比較やWebサーバ全体の再現ではない。Linux機能・ポリシーによりio_uringを使えない環境もある。
時間が押せばこのスライドは1文で進む。詳細な制約や過去の実験はREADMEからたどれる。
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
ここまで14分。残り1分は切り替えやトラブル用。リハーサルの実測欄をPRESENTERで記入する。
-->
