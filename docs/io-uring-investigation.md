# Zig 0.17.0 / io_uringの再調査

確認日：2026-10-18。Linux環境：`orb -m zig-syscall-lab`、aarch64、Linux 7.0.14。コンパイラ：`/home/mimoc/.zvm/0.17.0/zig`（version 0.17.0）。

## 結論

**Zig 0.17.0でio_uring自体は実行できている。失敗するのはstd.Io.Eventedの抽象化経由。**

| 経路 | 再確認の結果 |
| --- | --- |
| `std.os.linux.IoUring` | リングの作成・要求のsubmit・CQE取得に成功。128 byteを読み取り |
| `std.Io.Threaded` | 共通app()がHello, World!を出力。writevを確認 |
| `std.Io.Evented` → `std.Io.Uring` | 配布標準ライブラリ内のVTable不整合でコンパイル失敗。実行に到達しない |

## 低レベルAPIの実測

```sh
orb -m zig-syscall-lab node scripts/check-linux.mjs
```

`snippets/io_uring_read.zig`は/dev/zeroから128 byteを読み取り、CQEのuser_dataとres、バッファ内容を検査する。今回追加したstraceの記録は`docs/validation-linux.json`の`uringTrace`。

実測の要点（PIDとsetupの構造体詳細は省略）：

```text
io_uring_setup(8, {...}) = 3
io_uring_enter(3, 1, 0, 0, NULL, 8) = 1
user_data=42, res=128
```

したがって、このVMでio_uringが利用不可、カーネルが非対応、seccompで拒否された、という説明は今回の失敗原因ではない。

## Eventedの原因

```sh
orb -m zig-syscall-lab node scripts/check-backends.mjs
```

Io/Uring.zigのio()が構築するVTableに`processReplacePath`を指定する一方、同じ配布物のIo.VTableにはこのフィールドがない。stdoutだけのapp()でもバックエンドのVTableを具体化するため、未使用のprocess操作に関する不整合がコンパイルを止める。processReplacePathをアプリが呼んだことが原因ではない。

実測エラー：

```text
lib/std/Io/Uring.zig:759:14: error: no field named 'processReplacePath' in struct 'Io.VTable'
```

アプリの初期化・引数処理・出力ロジックを取り除いた、以下の2行でも同じエラーを再現した（build-objのみ。実行しない）。

```zig
const std = @import("std");
export fn repro(backend: *std.Io.Evented) void { _ = backend.io(); }
```

```sh
zig build-obj /tmp/zig-lt-evented-repro.zig -fno-emit-bin
```

Zigは必要になった宣言を解析するため、Threadedや低レベルIoUringだけを使うプログラムが成功しても、このEventedの不整合は検出されない。

## 配布物との照合

[公式ダウンロード一覧](https://ziglang.org/download/index.json)を再確認。0.17.0は2026-10-01リリースで、公式ソースは[zig-0.17.0.tar.xz](https://ziglang.org/download/0.17.0/zig-0.17.0.tar.xz)。

- 公式一覧のソースアーカイブSHA256と、取得済みアーカイブの実測値が一致：`b6c7f1728f043700d6529bac980800792f824256a9d2f1839b3d62beed0b8abd`
- 公式アーカイブの`lib/std/Io/Uring.zig`、macOSの0.17.0、Linuxの0.17.0の同ファイルが一致：`7e7851e9c1fdcf111aa28448e7b40f944c664f82002f872e527753cd96279ab0`
- macOS/Linuxの`lib/std/Io.zig`も一致：`382a4e343017183eff88e311f983066f88306e7bfcd85a890723b3697f4b2732`

インストール済みライブラリを変更したことや、ローカルのUringファイルだけが古いことによる不整合ではなく、確認した公式0.17.0配布ソースにも存在する問題。

一時コピーでの追加調査では、旧`processSpawnPath`の指定と、新しい`inheritParentDir` / `inheritParentFile`の欠落も確認した。単純にエラー行を1行削除すれば利用できる、とは案内しない。インストール済み標準ライブラリを改変した実行結果や、別バージョンの結果を0.17.0の結果として扱っていない。

## 資料での扱い

低レベルIoUringの成功とEventedの失敗を明示的に分ける。Eventedの両バックエンド出力一致・io_uring_setup/enter比較は未完了。今後、標準ライブラリの修正版で再検証する必要がある。

パッチを当てる実験は別条件の検証になる。実施する場合は差分・バージョン・利用した経路を明示し、未改変0.17.0で実行できたとは説明しない。今回の再調査では、実測済みの低レベルAPIをio_uringの動作証拠とし、Eventedの性能や成熟度の証拠には使わない。
