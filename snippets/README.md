# std.Ioバックエンド差し替えデモ

対象は **Zig 0.17.0 / Linux**。`io_backend_demo.zig`内の同じ`app(io)`をThreadedとEventedから呼ぶ。アプリ本体は標準出力への`Hello, World!\n`の書き込みだけで、バックエンドの初期化と後始末は呼び出し側に置く。DIやio_uringは他の言語でも利用でき、このデモはZigの性能優位性を示さない。性能測定は行わない。

## 今回の結果（2026-10-18）

| バックエンド | 公式0.17.0での結果 |
| --- | --- |
| Threaded | ビルド・実行成功。`Hello, World!\n`、straceで`writev`を観測 |
| Evented | 標準ライブラリのコンパイルエラー。実行・出力一致・io_uring syscall比較は未確認 |

Eventedは実験的な実装。Linuxの`std.Io.Evented`は`std.Io.Uring`を選ぶが、0.17.0の`lib/std/Io/Uring.zig:759`が`Io.VTable`に存在しない`processReplacePath`フィールドを指定する。公式配布ソースとインストール済みソースの一致を確認した。標準ライブラリを改変して成功した結果として提示していない。

一時コピーでエラー原因を調査すると、`processSpawnPath`や`inheritParentDir` / `inheritParentFile`にも不整合があった。1行削除で解消するとは限らない。インストール済みライブラリと本デモは未改変の公式ライブラリを使う。

## 実行手順

### Eventedのコンパイル失敗だけを再現する

`evented_compile_failure.zig`は、ビルド設定や追加モジュールなしで失敗を再現する独立したプログラムです。Linux / 未改変のZig 0.17.0で、リポジトリルートから実行します。

```sh
zig build-exe snippets/evented_compile_failure.zig -fno-emit-bin
# このMacからLinux VMで確認する場合
orb -m zig-syscall-lab zig build-exe snippets/evented_compile_failure.zig -fno-emit-bin
```

期待される結果は終了コード1と、`Io.VTable`に`processReplacePath`フィールドがないというコンパイルエラーです。意図的な`@compileError`ではなく、実際にEventedを使用したときの標準ライブラリ内のエラーを再現します。macOSでは別のバックエンドになるため、Linuxで確認してください。

### バックエンド差し替えデモ

Linux、Zig 0.17.0、straceを用意し、リポジトリルートで実行する。このMacでは`orb -m zig-syscall-lab`でLinuxに入れる。

```sh
zig version
zig build --build-file snippets/build.zig -Dbackend=threaded --prefix /tmp/zig-lt-threaded
strace -f -e trace=write,writev,io_uring_setup,io_uring_enter,io_uring_register \
  -o /tmp/threaded.trace /tmp/zig-lt-threaded/bin/io_backend_demo \
  > /tmp/threaded.out
cat /tmp/threaded.out
cat /tmp/threaded.trace
```

実測からPIDを除いた行：

```text
writev(1, [{iov_base="Hello, World!\n", iov_len=14}], 1) = 14
```

Eventedも同じファイルをビルドする。ビルド時に選択するため、EventedのコンパイルエラーがThreadedの検証を妨げない。

```sh
zig build --build-file snippets/build.zig -Dbackend=evented --prefix /tmp/zig-lt-evented
```

今回の実測エラーの抜粋：

```text
lib/std/Io/Uring.zig:759:14: error: no field named 'processReplacePath' in struct 'Io.VTable'
```

**この状態ではEventedの実行ファイルは生成されない。** 修正版でビルドに成功した場合に限り、次を実行して結果を確認する。以下は再検証手順であり、成功済みの実測例ではない。

```sh
strace -f -e trace=write,writev,io_uring_setup,io_uring_enter,io_uring_register \
  -o /tmp/evented.trace /tmp/zig-lt-evented/bin/io_backend_demo \
  > /tmp/evented.out
cmp /tmp/threaded.out /tmp/evented.out
cat /tmp/evented.trace
```

両方が同じ出力を返すか、Eventedのtraceに成功した`io_uring_setup` / `io_uring_enter`があるかを確認する。ソースにそれらがあることと実測は区別する。環境によってはカーネル・seccomp等の制約で利用できない。失敗を隠してThreadedへ切り替える処理は入れていない。

## 初期化APIの確認

0.17.0配布ソースの`lib/std/Io.zig`、`Io/Threaded.zig`、`Io/Uring.zig`を確認した。

```zig
// Threaded: initは値を返す
var backend = std.Io.Threaded.init(init.gpa, .{});
defer backend.deinit();
try app(backend.io());
```

```zig
// Evented: 未初期化の変数に対し、失敗し得るinitを呼ぶ
var backend: std.Io.Evented = undefined;
try backend.init(init.gpa, .{});
defer backend.deinit();
try app(backend.io());
```

`Io.Evented`はOSとfiber対応に応じた型の選択。LinuxではUring、macOSではDispatch、非対応targetではvoid。Threaded / Evented / Uringを独立した3種類として扱わない。Uring.initのソースはCOOP_TASKRUN / SINGLE_ISSUERフラグを使ってリングを初期化するが、今回Eventedのstraceでは観測していない。

## 検証記録の更新

```sh
npm run check:backends
```

Linux上で2種類のビルドを試し、実行できたものだけをstraceで確認して`docs/validation-backends.json`に保存する。終了コード0は記録処理と既知の状態の確認が成功した意味であり、両バックエンドの成功を意味しない。`comparisonCompleted`がfalseなら比較は未完了。

低レベルの`io_uring_read.zig`は別のAPI（`std.os.linux.IoUring`）の例。これが動いても、`std.Io.Evented`が動いた証拠にはならない。

出典：[Zig 0.17.0](https://ziglang.org/download/0.17.0/release-notes.html)、[標準ライブラリ](https://ziglang.org/documentation/0.17.0/std/)、[writev(2)](https://man7.org/linux/man-pages/man2/writev.2.html)、[io_uring_setup(2)](https://man7.org/linux/man-pages/man2/io_uring_setup.2.html)。
