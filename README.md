# Zigで覗く、Linuxの非同期I/O

Webエンジニア向けの15分LT。Slidev製、全23枚。普段のasync/awaitからLinuxのI/O機構に興味を持ち、Zigで観察して得た発見を共有します。冒頭のhotoさんのPython非同期処理LTへの言及は、タイトルの発表者ノートにある口頭説明です。

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
3. 最近よく聞く io_uring
4. ところで、Zigとは？
5. Zigでシステムコールを試す
6. システムコールは、OSへの依頼
7. fdは、プロセスが持つ番号
8. データがまだないとき、どうする？
9. なぜepollは低Ready率に強い？
10. Kerrisk氏の測定を、CとZigで追試
11. 動的に切り替えれば速くなる？
12. io_uringは、I/Oを依頼して完了を受け取る
13. 同じ受信処理を、3方式で実測
14. epollは「I/Oできる状態」を教える
15. 「準備完了」と「操作完了」の違い
16. Zigのstd.Ioで、I/O実装を分離する
17. 同じコードで、syscallは変わる？
18. std.Ioにも、実装ごとの対応差がある
19. I/Oを差し替えられると、何がうれしい？
20. io_uringなら、何でも速い？
21. 使いたくても使えないことがある
22. 非同期I/Oの裏側を覗いてみた
23. 参考資料

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

[Linux実測記録](docs/validation-linux.json)、[技術レビューと検証範囲](docs/technical-review.md)を参照してください。これらのスニペット検証には、Docker内の拒否やUringのキャンセル実行は含みません。

## バックエンド差し替えデモ

[デモのコード](snippets/io_backend_demo.zig)と[実行手順](snippets/README.md)を追加しました。同じapp()を使い、`-Dbackend=threaded` / `evented`で呼び出し側の初期化だけを選びます。

**公式Zig 0.17.0では比較を完了できていません。** Threadedは`Hello, World!\n`を出力し、straceでwritevを確認しました。EventedはUringのVTable不整合（processReplacePath）でコンパイルに失敗し、実行・出力一致・io_uring_setup/enterは未確認です。標準ライブラリ未改変での[記録](docs/validation-backends.json)を掲載しています。既存の低レベルIoUringサンプルの成功とは区別してください。性能比較はしていません。

再調査の原因・最小再現例・io_uring syscallの実測は[調査記録](docs/io-uring-investigation.md)にまとめています。低レベルAPIでのio_uring実行は成功し、Eventedのコンパイル失敗とは区別しています。

## poll / epollの比較実験

[ベンチマークの実行・再分析手順](benchmarks/poll-epoll/README.md)を参照してください。Zig 0.17.0のLinux APIを直接使い、readiness取得とバースト型End-to-Endを別々に測定し、送信・受信区間も分解します。

```sh
orb -m zig-syscall-lab sh benchmarks/poll-epoll/run.sh --output /tmp/poll-epoll-new
orb -m zig-syscall-lab python3 benchmarks/poll-epoll/analyze.py /tmp/poll-epoll-new
```

低Ready率ではepoll優位、高Ready率では差が縮小しました。送信込みの再測定では4096fd・全Ready・1KiBで小さなpoll優位が再現したため、コストモデルによるAdaptiveも評価しました。各200msの動的負荷では改善未確認でしたが、モデルを固定した追加検証では高Ready区間1秒・5秒で改善を確認しました。条件と信頼区間は追加レポートに掲載しています。raw JSONL、集計CSV、SVGグラフ、測定環境を保存しています。本番Webサーバの継続的な並行到着を再現するものではありません。

追加監査の[原因分析レポート](benchmarks/poll-epoll/ANALYSIS.md)では、待機APIと送信側の費用を区別し、送信順の対照・CPU割当・Adaptiveの区間別挙動と高Ready区間の延長を検証しています。過去のrawと分析ファイルは保持しています。

Kerrisk氏の講義資料を追試した[独立C/Zig再構成実験](benchmarks/poll-epoll/kerrisk-reproduction/README.md)と[結果レポート](benchmarks/poll-epoll/kerrisk-reproduction/REPORT.md)も追加しました。元Cソースは未入手のため厳密再現ではなく、仮定と実測を分け、100万反復の結果・対照・再生成可能なCSV/SVGを保存しています。

## io_uringの実受信比較

[実行手順と設計](benchmarks/poll-epoll/io-uring/README.md) / [実測レポート](benchmarks/poll-epoll/io-uring/ANALYSIS.md)。Zig 0.17.0のstd.os.linuxでRECV/POLL_ADDを動かし、同一系列のpoll/epollと送信・受信・内容検証込みで比較しました。基本32条件ではRECVがepollの速度中央値を上回らず、バッチ化によるenter/CPU削減と全体性能を区別しています。初期化と未完了要求の終了費用、全raw・CSV・SVGも保存しています。std.Io.Eventedの測定ではありません。
