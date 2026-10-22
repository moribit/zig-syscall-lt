# ZigでLinuxのI/Oを観察する

Zig **0.17.0** / Linux。今回の実演環境はmacOS上の **OrbStack / Fedora / aarch64**。
5本とも単一ファイルで、libc・liburing・ベンチマークのコードに依存しない。
性能比較ではなく、依頼と結果を見るためのサンプル。

| デモ | 観察すること | データ |
|---|---|---|
| `00-write.zig` | raw writeと戻り値 | stdoutへ`hello\n`（6 byte） |
| `01-blocking.zig` | 空のpipeのreadが本当に待つ | 1秒後に`hello`（5 byte） |
| `02-poll.zig` | EAGAIN、fd一覧、Ready通知、その後のread | 2本中pipe Bへ`hello` |
| `03-epoll.zig` | ADDで登録、waitでReady通知、その後のread | 同じ2本・同じ`hello` |
| `04-io-uring.zig` | oneshot READのSQE、submit、CQE、buffer | pipeへ同じ`hello` |

## 最初の準備

MacからLinuxへ入る。以下のビルド・実行コマンドはLinuxの中で使う。

```sh
orb -m zig-syscall-lab
cd /Users/mimoc/zig-syscall-lt
zig version # 0.17.0
sh demos/check.sh
```

`zig`、`strace`、GNU `timeout`、`readelf`が必要。`check.sh`はLinux/バージョンを検査し、
ReleaseSafeで全5本を事前ビルド、動的ライブラリ依存を確認し、各20回＋strace1回を実行する。
初回ビルドを含むため数分見込む。終わったら`demos/.build/`のバイナリを本番で使う。
検証先を再利用しない設計なので、再検証時には新しい出力先を指定する。

```sh
DEMO_CHECK_OUTPUT=/tmp/lt-demo-check-new sh demos/check.sh
```

カーネルやseccompのセキュリティ設定は変更しない。

## 実行

要求どおり各ファイルを単独でも実行できる。

```sh
zig run demos/00-write.zig
zig run demos/01-blocking.zig
zig run demos/02-poll.zig
zig run demos/03-epoll.zig
zig run demos/04-io-uring.zig
```

本番はビルド済みを使う。番号だけで選べる。

```sh
sh demos/run.sh 2 --source # ソース表示（batがあればシンタックスハイライト）
sh demos/run.sh 2          # 実行
sh demos/run.sh 2 --trace  # strace付き
sh demos/run.sh 2 --saved  # 保存した成功出力（ライブ実行と混同しない）
```

`std.debug.print`による説明ログはstderr。デモ0のhelloだけstdoutへ書く。
ログやstraceは実際のfd番号を表示する。pipeには読み取り側と書き込み側の別fdがある。
fdの固定値は仮定しない。

## 期待する順序

* write：hello → requested=6, returned=6。
* blocking：read waiting → 1秒後writer → returned=5, buffer=hello。
* poll：空pipeでEAGAIN → no fd ready → writer → pipe BがReady → read hello。
* epoll：instance作成 → ADD2件 → wait → pipe BがReady → read hello。
* io_uring：ring作成 → SQE READ, user_data=42 → submit → writer → CQE 42 / res=5 → buffer hello。

poll/epollはデータを読まないので、その後のreadを指す。
io_uringではREADを頼んだ結果としてbufferにデータがある。`res<0`なら負のerrno。
同一pipeへ1回だけ5 byteをatomic writeする、制御されたデモ。一般的なbyte streamの
レコード復元や本番サーバの実装ではない。予期しない短いread/writeは成功と扱わずエラーにする。
EINTRなどの予期しない割り込みも失敗として止めるため、黙って違う動作を見せない。

## straceで見る

子スレッドも追うため`-f`、時刻とsyscall所要時間を表示するため`-tt -T`を使う。

```sh
strace -f -tt -T -e trace=pipe2,poll,ppoll,read,write demos/.build/02-poll
strace -f -tt -T -e trace=epoll_create1,epoll_ctl,epoll_wait,epoll_pwait,read,write demos/.build/03-epoll
strace -f -tt -T -e trace=io_uring_setup,io_uring_enter,io_uring_register,read,write demos/.build/04-io-uring
```

実演ではtimeout付きの`run.sh --trace`を推奨。
aarch64ではZigの`linux.poll`が`ppoll`、`epoll_wait`が`epoll_pwait`を呼ぶ。
x86_64などではsyscall名が異なり得る。0ms待機は空状態の確認で、その後が実際の待機。

blockingの保存straceではreadが約1秒かかり、別スレッドのwrite後に戻る。
睡眠はwriterの到着を遅らせるだけで、readerをsleepで代用していない。
io_uringのsetup/mmapは初期化、enterは投入/完了待機。今回registerは不要なので呼ばれない。
SQEの準備・CQE回収は共有メモリ操作であり、straceに独立したsyscallとしては出ない。
READの処理が通常の`read(fd,...)`という行に現れなくても不自然ではない。
pipeの読み取りはカーネル内部のpoll等で進み得るが、その実装経路をstraceだけから断定しない。

## 検証結果と退避

`recordings/validation-orbstack/`に環境・ソース/ELFハッシュ・全100回のログ・5本のstraceを保存。
Linux 7.0.14-orbstack / Fedora 44 / aarch64 / Zig 0.17.0で **全5本×20回成功**。
ELFにINTERP/NEEDEDなし。検証時のGit SHAは作業開始時のもので、ソースの実体はsha256.txtで識別する。
標準ライブラリとカーネルの既定実装を利用し、SQPOLL・multishot・provided bufferは使わない。
過去のmultishot EOF問題のコードとは独立している。

`recordings/00-write.log`等は成功時の保存出力。障害時は「保存ログです」と伝えて表示する。
straceも`recordings/validation-orbstack/04-io-uring.strace`等を表示できる。
**当日の環境で再実行**すること。VM更新後も同じとは限らない。

## 止まる・使えないとき

* Macで直接実行：Linuxが必要。OrbStackへ入る。
* コンパイル失敗：`zig version`と`PATH`を確認。0.17.0以外は検証対象外。
* io_uring初期化失敗：エラー名とstraceのerrno、`/proc/sys/kernel/io_uring_disabled`、seccompを確認。
  EPERMをカーネル未対応と即断しない。設定を広く緩めず保存ログへ切り替える。
* 通常実行は10秒、straceは12秒でtimeout。blocking/io_uringは直接実行にも8秒のSIGALRM上限。
  poll/epollは3秒の待機上限とnon-blocking readを使う。失敗したwriterはpanicでプロセスごと停止する。
* threadはjoinし、pipe/epoll/ringはdeferで解放する。投入済みREADの不明なエラーは
  bufferを先に解放せずプロセスをabortする。カーネルが参照するbufferはCQEまで生存する。
* 手動中断はCtrl-C。外部サービス、FIFO、バックグラウンドデーモンは作らない。

再ビルド時に`demos/.build/`だけ削除してよい。保存済みrecordingsやbenchmarksは削除しない。
当日の順序と時間配分は[PRESENTER.md](PRESENTER.md)。

一次資料：[poll(2)](https://man7.org/linux/man-pages/man2/poll.2.html)、
[epoll(7)](https://man7.org/linux/man-pages/man7/epoll.7.html)、
[io_uring(7)](https://man7.org/linux/man-pages/man7/io_uring.7.html)。
