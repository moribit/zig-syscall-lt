# Zigで覗く、Linuxの非同期I/O

Webエンジニア向けの15分前後のLT。Slidev製、全20枚。Zig 0.17.0の短いプログラムとstraceで、write・blocking read・poll・epoll・io_uringを実演します。コード全文はターミナルで見せ、スライドには概念図と3行以下の呼び出し抜粋を載せています。今回の実演・検証環境はmacOS上のOrbStack / Fedora Linuxです。

**当日の入口：[demos/README.md](demos/README.md) / [操作と進行の目安](demos/PRESENTER.md)**。Linux内で `sh demos/check.sh` を実行して事前ビルドし、本番は `sh demos/run.sh 2 --trace` のように使います。

## 起動・出力

```sh
npm install
npm run dev
npm run build
npm run export
```

開発サーバーは http://localhost:3030 。矢印キー/Spaceで段階表示、`p`で発表者モード、`o`で一覧表示。PDFは[output/pdf/zig-linux-async-io.pdf](output/pdf/zig-linux-async-io.pdf)、Web版は`dist/`に出力します。Chromiumがない場合は`npx playwright install chromium`で導入するか、`npm run export -- --executable-path /path/to/chromium`を使ってください。

## 構成

1. タイトル
2. async/await の下では何が起きている？
3. Zigとは？（writeミニデモ）
4. システムコールは、OSへの依頼（write抜粋）
5. fdとblocking readミニデモ
6. データがないとき、どう待てばいい？
7. poll（区切り）
8. pollの仕組み（fd一覧・revents）
9. pollライブデモ
10. epoll（区切り）
11. epollの仕組み（初期登録と待機）
12. epollライブデモ
13. io_uring（区切り）
14. io_uringの仕組み（SQE→submit→CQE）
15. io_uringライブデモ
16. ReadinessとCompletion
17. 同じhelloを受け取る、3つの方法
18. 観察して分かったこと
19. まとめ
20. デモと参考資料

15分前後を目安に、分かりやすさを優先します。デモを含む進行目安は約17分で、操作の遅延や質疑は別に見込みます。リハーサルの実測欄は[PRESENTER](demos/PRESENTER.md)を使ってください。

性能比較・Adaptive・Kerrisk追試・std.Ioの詳細は本編から外しました。既存のベンチマーク・raw・グラフ・分析は維持し、[旧23枚と当時のREADME](docs/archive/pre-live-demo-ae3ee2a/)も保存しています。以下の旧検証項目・実験レポートは補足資料です。

## 編集

- `slides.md`：本文・編集可能なHTML図・各ページ末尾の発表者ノートと出典
- `styles/index.css`：ダーク背景・明るい文字、図と余白、コードのコントラスト
- `layouts/api-section.vue`：API名だけを中央に置く共通区切り
- `components/IoFlow.vue`：Application左・Kernel右の共通図
- `setup/shiki.ts`：構文ハイライトと説明に対応する色
- `global-bottom.vue`：ページ番号
- `demos/`：今回のライブデモ5本・事前ビルド/検証・成功ログ・当日手順
- `snippets/`：従来のZig 0.17.0実行例（補足）

青はfd、緑はバッファ/データ、紫はbyte数・結果・user_data、茶は操作。同じ意味を図と説明で対応させ、ラベルも併記しています。各方式に3行以下のコード抜粋を置き、同じ色を図とコードへ対応させています。戻り値・エラー処理を含む全文はデモで表示します。SQ/CQは4クリックで段階表示し、PDFには最終状態を出力します。

旧15枚版も[docs/archive/pre-visual-373d301](docs/archive/pre-visual-373d301/)へ本文・スタイル・PDFを保存しています。

## ライブデモの検証

OrbStack / Linux 7.0.14 / aarch64 / Zig 0.17.0で全5本×20回とstrace確認に成功。ログ・ソースハッシュ・ELF確認は[demos/recordings/validation-orbstack](demos/recordings/validation-orbstack)に保存しています。fdのcloseも確認しました。

```sh
# Linux内で実行
sh demos/check.sh
# Slidevビルド後に表示を確認
npm run check:visual
# 掲載した8つのAPI呼び出しとデモを照合
npm run check:slides
```

## 旧スニペット・補足資料の検証

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

[実行手順と設計](benchmarks/poll-epoll/io-uring/README.md) / [実測レポート](benchmarks/poll-epoll/io-uring/ANALYSIS.md)。Zig 0.17.0のstd.os.linuxでRECV/POLL_ADDを動かし、同一系列のpoll/epollと送信・受信・内容検証込みで比較しました。実機追試では基本32条件のうち6条件でRECV/epollのペア速度比中央値が1を超えました。VM系列と分け、バッチ化によるenter/CPU削減と全体性能を区別しています。初期化と未完了要求の終了費用、全raw・CSV・SVGも保存しています。std.Io.Eventedの測定ではありません。

最新の[Linux実機での結果](benchmarks/poll-epoll/io-uring/PHYSICAL_ANALYSIS.md)は、Intel i7-3615QM / EndeavourOS / Linux 6.18.9 x86_64 / Zig 0.17.0で測定しました。主系列1520件とSQ対照80件を新しいresultsへ保存し、io_uring実測スライドを実機の値へ更新しています。Kerrisk/Adaptiveは過去のVM系列として保持しています。

継続到着型の追加実験は[事前計画](benchmarks/poll-epoll/io-uring/CONTINUOUS_DESIGN.md)・[実行手順](benchmarks/poll-epoll/io-uring/continuous/README.md)・[検証レポート](benchmarks/poll-epoll/io-uring/CONTINUOUS_ANALYSIS.md)を参照してください。epoll・oneshot・provided-buffer multishotを実装しましたが、実機6.18.9でmultishotのEOF検証が停止したため、探索・独立確認の性能測定はまだ行っていません。上流のEOF競合修正と照合し、失敗ログも保存しています。
