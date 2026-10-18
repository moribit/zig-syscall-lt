# Zigで覗く、Linuxの非同期I/O

Webエンジニア向けの15分LT。Slidev製、全20枚。普段のasync/awaitからLinuxのI/O機構に興味を持ち、Zigで観察して得た発見を共有します。冒頭のhotoさんのPython非同期処理LTへの言及は、タイトルの発表者ノートにある口頭説明です。

## 起動・出力

```sh
npm install
npm run dev
npm run build
npm run export
```

開発サーバーは http://localhost:3030 。矢印キー/Spaceで段階表示、`p`で発表者モード、`o`で一覧表示。PDFは[output/pdf/zig-linux-async-io.pdf](output/pdf/zig-linux-async-io.pdf)、Web版は`dist/`に出力します。Chromiumがない場合は`npx playwright install chromium`で導入するか、`npm run export -- --executable-path /path/to/chromium`を使ってください。

## 構成

1. Zigで覗く、Linuxの非同期I/O
2. async/await の下では何が起きている？
3. 最近よく聞く io_uring（PostgreSQL 18 / Dragonfly / Node.js・libuv）
4. ところで、Zigとは？
5. Zigのコードが、そのままsyscallに見える
6. システムコールは、OSへの依頼
7. fdは、プロセスが持つ番号
8. データがまだないとき、どうする？
9. io_uringは、I/Oを依頼して完了を受け取る
10. なぜio_uringは速くなり得る？
11. epollは「I/Oできる状態」を教える
12. 「準備完了」と「操作完了」の違い
13. Zigのstd.Ioで、I/O実装を分離する
14. 同じコードで、syscallは変わる？（Threaded実測 / Eventedビルド障害）
15. std.Ioにも、実装ごとの対応差がある
16. I/Oを差し替えられると、何がうれしい？
17. io_uringなら、何でも速い？
18. 使いたくても使えないことがある
19. 非同期I/Oの裏側を覗いてみた
20. 参考資料

## 編集

- `slides.md`：本文・編集可能なHTML図・各ページ末尾の発表者ノートと出典
- `styles/index.css`：白背景・黒文字、図と余白、ダークコード背景
- `setup/shiki.ts`：構文ハイライトと説明に対応する色
- `global-bottom.vue`：ページ番号
- `snippets/`：Zig 0.17.0の完全な実行例

青はfd/I/Oインターフェース、緑はバッファ、紫はbyte数・結果、茶は操作。白背景の説明とダーク背景のコードで同じ色相を使い、ラベルも併記しています。SQ/CQ、epollの流れ、両方式の比較はクリックで段階表示します。PDFには最終状態を出力します。

## 検証

Zig **0.17.0**、Node.jsが必要です。Linux固有コードの実行にはLinuxを使ってください。

```sh
npm run check:snippets
zig test tests/future_contract.zig
# Linux上で実行（straceも必要）
npm run check:linux
# バックエンド別のビルドとstraceを記録
npm run check:backends
# ビルド後、Chromiumで全ページ・クリック・発表者ノートを確認
npm run check:visual
# システムのChromiumを使う場合
CHROMIUM_PATH=/path/to/chromium npm run check:visual
```

`check:snippets`は本文のZig抜粋3件と完全なプログラム5件を、x86_64-linux / aarch64-linux向けにコンパイルし、JavaScript 1件を構文チェックします。`ZIG=/path/to/zig`でコンパイラを指定できます。

今回の実行環境は`orb -m zig-syscall-lab`（Fedora / aarch64、Linux 7.0.14、Zig 0.17.0）。共有ディレクトリで`npm run check:linux`を実行しました。SlidevはVM内の`/tmp/zig-lt-slidev`にLinux用依存関係を導入してビルド・PDF出力しました。macOSの`node_modules`をLinuxで共用しないでください。

| 実行例 | 確認結果 |
| --- | --- |
| `raw_write.zig` | `hello`を6 byte出力。straceでも`write(1, "hello\n", 6) = 6` |
| `raw_read.zig` | stdinの読み取りと出力。空入力・バッファより長い入力も確認 |
| `io_basic.zig` | `std.process.Init`のI/Oで`hello`を出力 |
| `io_injection.zig` | 同じ`app(io)`がThreadedで成功、`std.Io.failing`で`InputOutput` |
| `io_uring_read.zig` | `/dev/zero`から128 byte、CQEの`user_data=42, res=128` |

[Linux実測記録](docs/validation-linux.json)、[技術レビューと検証範囲](docs/technical-review.md)を参照してください。性能ベンチマーク、Docker内の拒否、Uringのキャンセル実行は今回の検証には含みません。

## バックエンド差し替えデモ

[デモのコード](snippets/io_backend_demo.zig)と[実行手順](snippets/README.md)を追加しました。同じapp()を使い、`-Dbackend=threaded` / `evented`で呼び出し側の初期化だけを選びます。

**公式Zig 0.17.0では比較を完了できていません。** Threadedは`Hello, World!\n`を出力し、straceでwritevを確認しました。EventedはUringのVTable不整合（processReplacePath）でコンパイルに失敗し、実行・出力一致・io_uring_setup/enterは未確認です。標準ライブラリ未改変での[記録](docs/validation-backends.json)を掲載しています。既存の低レベルIoUringサンプルの成功とは区別してください。性能比較はしていません。
