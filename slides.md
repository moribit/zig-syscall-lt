---
theme: default
title: Zigで見る非同期I/OとLinuxシステムコール
info: |
  Webエンジニア向けLT。fd、read/write、epoll、io_uring、std.Ioをつなぐ。
author: ''
class: cover
layout: default
colorSchema: light
aspectRatio: 16/9
canvasWidth: 1100
transition: fade
fonts:
  sans: 'Noto Sans JP'
  mono: 'JetBrains Mono'
  provider: none
drawings:
  enabled: false
download: false
---

<div class="eyebrow">ZIG / LINUX I/O</div>

# Zigで見る<br>非同期I/Oと<br>Linuxシステムコール

<div class="cover-sub">read / write / fd / epoll / <strong>io_uring</strong> / std.Io</div>

<div class="cover-bottom">Webの async/await を、OSの入口から理解する</div>

<!--
元資料: zig_async_syscalls_lt_webfriendly.pdf。全15枚の構成を引き継ぐ。
想定聴衆はJavaScriptのasync/awaitを使ったことのあるWebエンジニア。
元資料の環境表記はZig 0.17 / Fedora on OrbStack。std.Ioの解説は確認できた0.16公式リリースノートに基づく。APIは利用バージョンで確認する。
-->

---

<div class="eyebrow">01 / SYSTEM CALL</div>

# Zigの1行が、syscallに見える

```zig
const n = std.os.linux.write(1, "hello\n", 6);
```

<div class="terminal-label">Linuxでビルドして strace で観察</div>

```sh
$ zig build-exe hello.zig
$ strace -e write ./hello
write(1, "hello\n", 6) = 6
```

<div class="inline-defs"><span class="ref-fd"><b>1</b> 出力先のfd</span><span class="ref-buffer"><b>"hello\n"</b> 書き込むbytes</span><span class="ref-result"><b>6 / n</b> 要求数 / 実際のbyte数</span></div>

<div class="takeaway">std.os.linux から、Linux syscallに近い層を触れる</div>

<!--
コードはmain関数内の抜粋。nは後で利用するか、_ = n; として未使用を明示する。
libcのwriteラッパーを経由する前提ではない。strace出力は元PDFの例であり、この環境での実測ではない。
writeは要求より短く書くことがある。raw APIの返り値ではエラー判定も必要。
https://man7.org/linux/man-pages/man2/write.2.html
-->

---

<div class="eyebrow">02 / FILE DESCRIPTOR</div>

# fdは、プロセス内の番号

<div class="columns">
<div>

| fd | 接続先の例 |
| --- | --- |
| <span class="ref-fd">0</span> | <span class="ref-fd">標準入力 stdin</span> |
| <span class="ref-fd">1</span> | <span class="ref-fd">標準出力 stdout</span> |
| <span class="ref-fd">2</span> | <span class="ref-fd">標準エラー stderr</span> |
| 3 | hello.txt |
| 4 | socket |

</div>
<div>

### 同じread/writeで扱う

ファイルも、socketも、pipeも<br>fdを通してアクセスする。

### シェルのリダイレクト

```sh
./main 1> out.txt
command 2>&1
```

番号は同じでも、接続先は変わる。

</div>
</div>

<div class="takeaway">fdの番号は、そのプロセスのfdテーブルで意味を持つ</div>

<!--
0/1/2は通常の起動時の割り当て。閉じたり付け替えたりできる。別プロセスのfd 3が同じ対象を指すとは限らない。
2>&1はその時点のfd 1をfd 2に複製する。リダイレクトの順序で結果が変わる。
https://man7.org/linux/man-pages/man2/open.2.html
-->

---

<div class="eyebrow">03 / RAW I/O</div>

# read / writeは、byte数を扱う

```zig
const linux = @import("std").os.linux;
var buf: [10]u8 = undefined;

const n = linux.read(0, &buf, buf.len);
if (linux.errno(n) != .SUCCESS) return; // エラー処理は省略
_ = linux.write(1, &buf, n);             // 読めた範囲だけ渡す
```

<div class="columns compact">
<div>

### readは「1行読む」関数ではない
<span class="ref-fd">0はstdin、1はstdout。</span><br>HTTPのbodyも少しずつ読む。

</div>
<div>

### 1回で全部とは限らない
<span class="ref-result">nは実際に読めたbyte数。</span><br><span class="ref-buffer">bufはbyte列の一時置き場。</span>

</div>
</div>

<div class="takeaway">次の疑問は「データを待つ間、このスレッドはどうなる？」</div>

<!--
流れを示す抜粋で、完全なecho実装ではない。writeのエラーとpartial write、readのEINTRへの再試行は省略。
readが0を返す場合はEOFなどを意味する（要求長が0の場合を除く）。端末のcanonical modeでは通常Enterまで入力をためる。
raw std.os.linuxのエラーはusizeにエンコードされる。エラーをbyte数としてwriteに渡してはいけない。
https://man7.org/linux/man-pages/man2/read.2.html
https://man7.org/linux/man-pages/man2/write.2.html
-->

---

<div class="eyebrow">04 / BLOCKING</div>

# Blocking I/Oとスレッドの待ち時間

<div class="sequence"><span>read(fd)</span><span class="waiting">データ待ち</span><span>データ到着</span><span>return</span></div>

<p class="big-statement">呼び出したスレッドは、<br><strong>待っている間、先へ進まない。</strong></p>

<div class="columns compact">
<div>

### 1接続なら分かりやすい
処理の順序が、そのままコードになる。

</div>
<div>

### 多数の接続をどう待つ？
接続ごとのスレッド以外に、event loopという選択肢がある。

</div>
</div>

<!--
待機中のスレッドがCPUを使い続ける、という意味ではない。通常はOSがスレッドをsleepさせる。
スレッド方式にも有効な用途がある。ここでは多数の接続を少ないスレッドで扱う動機を紹介する。
https://man7.org/linux/man-pages/man2/read.2.html
-->

---

<div class="eyebrow">05 / EAGAIN</div>

# Non-blockingは、読めなければ戻る

<div class="columns">
<div>

```text
read(fd, ...)

データがない
EAGAIN / EWOULDBLOCK

「今はまだ読めない」
```

</div>
<div>

### <span class="ref-operation">EAGAIN</span>とPromiseのpending
ただし、EAGAIN自体に再開を予約する仕組みはない。

### 繰り返すだけではbusy loop

```c
while (read(fd, buf, size) < 0) {
    // 即座に再試行し続けるのは避けたい
}
```

</div>
</div>

<div class="takeaway">「読めるようになったfd」をまとめて待つ仕組みがほしい</div>

<!--
Cコードはbusy loopの模式例。実際はerrnoを確認し、EAGAIN以外のエラーも扱う。
Promiseは値と完了通知の抽象化。EAGAINは1回のsyscallの結果であり、同じ仕組みではない。
https://man7.org/linux/man-pages/man2/read.2.html
-->

---

<div class="eyebrow">06 / REACTOR</div>

# epollは「I/Oできそう」を知らせる

<div class="columns">
<div>

### たくさんのfdを登録

```text
socket fd 5
socket fd 8      epoll_wait()
socket fd 12
```

</div>
<div>

### <span class="ref-fd">準備できたfd</span>を受け取る

```text
fd 8     EPOLLIN
fd 12    EPOLLOUT
```

通知を受けて、アプリが<span class="ref-operation">read/write</span>する。

</div>
</div>

<div class="takeaway">Reactor：準備完了の通知を受けて、自分でI/Oする</div>

<p class="fine">Edge-triggeredでは、non-blockingでEAGAINになるまで処理する。</p>

<!--
readinessは操作の完了ではない。read/writeでは引き続き返り値とEAGAIN等を扱う。
https://man7.org/linux/man-pages/man7/epoll.7.html
-->

---

<div class="eyebrow">07 / PROACTOR</div>

# io_uringは、操作の完了を受け取る

<div class="sequence uring"><span><small>SUBMISSION</small><b class="ref-operation">SQE</b><span class="ref-operation">read(fd)</span></span><span><small>EXECUTION</small><b>Kernel</b>I/Oを実行</span><span><small>COMPLETION</small><b class="ref-result">CQE</b><span class="ref-result">res = 128</span></span></div>

<div class="columns compact">
<div>

### epoll / Reactor
準備完了の通知を受ける。<br>その後、アプリがread/writeする。

</div>
<div>

### io_uring / Proactor
<span class="ref-operation">SQEに操作を記述する。</span><br><span class="ref-result">CQEから結果を受け取る。</span>

</div>
</div>

<div class="takeaway">SQ / CQは、ユーザー空間とカーネルで共有するリング</div>

<!--
SQE: Submission Queue Entry。CQE: Completion Queue Entry。resは成功時にbyte数など、エラー時は負のerrno。
SQEのuser_dataなどで要求と結果を対応付ける。完了順序は投入順と同じとは限らない。
バッファは操作が完了するまで有効に保つ。io_uring_enterなどのsyscallも使うため「syscallが不要」ではない。
すべての処理が常に非同期実行になる、または常に高速になる、とは限らない。
https://man7.org/linux/man-pages/man7/io_uring.7.html
-->

---

<div class="eyebrow">08 / JS ASYNC</div>

# JavaScriptのasync/await

```js
async function load(url) {
  const response = await fetch(url)
  const text = await response.text()
  return text
}
```

<div class="inline-defs"><span class="ref-result"><b>response / text</b> 受け取った結果</span><span class="ref-operation"><b>await</b> async関数の中断</span><span><b>runtime</b> 継続の再開</span></div>

<p class="big-statement smaller">同期処理のように書ける。<br>その下ではruntimeが、I/Oと再開を管理する。</p>

<div class="takeaway">ではZigでは、何を明示する？</div>

<!--
awaitはJSスレッド全体をブロックしない。Promiseの解決後、継続をmicrotaskとして実行する。
fetchの実装はブラウザやNode.js等のホストに依存する。JSのawait構文がio_uringを直接指定するわけではない。
https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/await
-->

---

<div class="eyebrow">09 / ZIG FUTURE</div>

# std.Ioで、関数呼び出しをtaskにする

<div class="columns code-wide">
<div>

```zig
// fetchLengthは、資源を返さずbyte数を返す関数
var future = io.async(fetchLength, .{ io, url });
defer _ = future.cancel(io) catch {};

doSomethingElse();

const length = try future.await(io);
```

</div>
<div>

### Futureのライフサイクル

1. <span class="ref-operation">async</span>で<span class="ref-result">future</span>を作る
2. 別の処理を進める
3. <span class="ref-operation">await</span>で結果を受け取る

<span class="ref-operation">cancel</span>でtaskの寿命を管理する。

</div>
</div>

<div class="takeaway">I/Oの実装を表す <span class="ref-fd">io</span> を、引数として明示的に渡す</div>

<p class="fine">std.Ioの説明はZig 0.16公式資料に基づく。コードは概念を示す抜粋。</p>

<!--
fetchLengthは!usizeを返す仮の関数。所有権のあるResponseを返す例では、cancelが成功した際の戻り値の解放も必要なので、元PDFの例を単純な値に変更。
asyncは並行実行を保証しない。直接呼び出してからFutureを返す実装も合法。
https://ziglang.org/download/0.16.0/release-notes.html#Future
-->

---

<div class="eyebrow">10 / ASYNC vs CONCURRENT</div>

# asyncとconcurrentは、要求が違う

<div class="columns">
<div>

### <span class="ref-operation">io.async</span>

```zig
var a = io.async(work, .{io});
defer _ = a.cancel(io) catch {};

const result = try a.await(io);
```

<strong class="ref-operation">他の処理から独立していてよい</strong>

実装がその場で呼び出し、<br>逐次実行してもよい。

</div>
<div>

### <span class="ref-operation">io.concurrent</span>

```zig
var task = try io.concurrent(work, .{io});
defer _ = task.cancel(io) catch {};

const result = try task.await(io);
```

<strong class="ref-operation">正しさのために並行実行が必要</strong>

提供できなければ<br>`error.ConcurrencyUnavailable`。

</div>
</div>

<div class="takeaway">並行実行を必須にするかどうかを、APIで伝える</div>

<!--
workは資源の解放が不要な値を返す関数を想定した抜粋。
concurrentはCPUコア上の並列実行そのものを保証する表現ではない。
https://ziglang.org/download/0.16.0/release-notes.html#Future
-->

---

<div class="eyebrow">11 / JS vs ZIG</div>

# I/Oの実行戦略を、どこに置くか

<div class="columns">
<div>

### JavaScript

```js
const a = fetch(urlA)
const b = fetch(urlB)

const ra = await a
const rb = await b
```

event loopやPromiseの実行基盤は<br>ホストruntimeが提供する。

</div>
<div>

### Zig / std.Io

```zig
var a = io.async(fetchLength, .{io, urlA});
var b = io.async(fetchLength, .{io, urlB});
// deferによるcancelは省略
const ra = try a.await(io);
const rb = try b.await(io);
```

呼び出し側から<span class="ref-fd">io</span>を渡し、<br>I/Oの実行戦略を選ぶ。

</div>
</div>

<div class="takeaway">Threadedなどの実装を、同じインターフェース越しに利用する</div>

<p class="fine">0.16公式資料ではEventedは実験段階、Uringは概念実証。対応状況はバージョンごとに確認。</p>

<!--
元PDFの「Threaded / Evented / Uringを差し替え可能」に実装成熟度の補足を加えた。
https://ziglang.org/download/0.16.0/release-notes.html#I/O-as-an-Interface
-->

---

<div class="eyebrow">12 / ROADMAP</div>

# syscallからasyncまでの学習順序

<div class="roadmap">
<div><b>01</b><strong>fd / read / write</strong><span>byte列と戻り値</span></div>
<div><b>02</b><strong>open / close</strong><span>資源の寿命</span></div>
<div><b>03</b><strong>non-blocking</strong><span>EAGAINと再試行</span></div>
<div><b>04</b><strong>poll / epoll</strong><span>準備完了の通知</span></div>
<div><b>05</b><strong>io_uring</strong><span>操作と完了のキュー</span></div>
<div><b>06</b><strong>std.Io</strong><span>実行戦略の抽象化</span></div>
</div>

<div class="takeaway">低レイヤを知ると、async/awaitの下にある「待ち方」が見える</div>

<!--
元PDFのロードマップを保持。read/writeのエラー処理とpartial I/Oを確認してから、待機方式を比較すると理解しやすい。
-->

---

<div class="eyebrow">13 / SUMMARY</div>

# 持ち帰ってほしいこと

<div class="summary-list">
<div><b>01</b><strong>fdは番号</strong><span>ファイルもsocketも、プロセスのfdテーブルに入る。</span></div>
<div><b>02</b><strong>I/Oはbyte列</strong><span>実際に扱えたbyte数と、エラーを確認する。</span></div>
<div><b>03</b><strong>非同期は待ち方の設計</strong><span>epollは準備完了、io_uringは操作完了を通知する。</span></div>
<div><b>04</b><strong>Zigはioを渡す</strong><span>呼び出す処理と、I/Oの実行戦略を分ける。</span></div>
</div>

<div class="takeaway">次に試すなら、echo serverでepollとio_uringを比べる</div>

<!--
性能比較はここでは実施していない。負荷、操作、カーネル設定等で結果は変わる。
-->

---

<div class="eyebrow">14 / SOURCES</div>

# 参考資料

<div class="sources">

- [Zig 0.16.0 Release Notes](https://ziglang.org/download/0.16.0/release-notes.html)<br><span>I/O as an Interface / Future / asyncとconcurrent</span>
- [Linux man-pages: read(2)](https://man7.org/linux/man-pages/man2/read.2.html) / [write(2)](https://man7.org/linux/man-pages/man2/write.2.html) / [open(2)](https://man7.org/linux/man-pages/man2/open.2.html)<br><span>fd、byte数、partial I/O、エラー</span>
- [Linux man-pages: epoll(7)](https://man7.org/linux/man-pages/man7/epoll.7.html) / [io_uring(7)](https://man7.org/linux/man-pages/man7/io_uring.7.html)<br><span>readinessとcompletion、SQとCQ</span>
- [JavaScript: await](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/await)<br><span>Promiseとasync関数の再開</span>

</div>

<p class="fine">ベース資料：zig_async_syscalls_lt_webfriendly.pdf（全15ページ）<br>元資料の環境：Zig 0.17 / Fedora on OrbStack / strace / zman</p>

<!--
元PDFが挙げた0.17.0リリースノートは今回確認できなかったため、確認できた0.16公式資料を掲載。
std.Ioに関するコードは概念説明の抜粋。実際のAPIは使用するZigバージョンの標準ライブラリで確認する。
-->
