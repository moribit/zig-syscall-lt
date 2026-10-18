# 技術レビュー・検証記録

確認日：2026-10-18。対象：Zig 0.17.0、Linux、Slidev 53。23枚、約15分。hotoさんのLTへの言及はタイトルの口頭説明に限定した。

## 根拠と修正

| 論点 | 採用した説明・修正理由 | 一次資料 |
| --- | --- | --- |
| async/await | 構文自体がepollを呼ぶわけではない。runtimeがOSの仕組みを使う経路の一例。PythonのProactorやfsのthreadpoolなど経路は異なる | [libuv design](https://docs.libuv.org/en/v1.x/design.html)、[Python event loops](https://docs.python.org/3/library/asyncio-eventloop.html#event-loop-implementations) |
| PostgreSQL 18 | AIO基盤を導入。workerが既定、io_uringは対応ビルドで選択。公式の最大3倍は特定条件のAIO全体の効果であり、io_uring単独の測定値ではない | [発表](https://www.postgresql.org/about/news/postgresql-18-released-3142/)、[io_method](https://www.postgresql.org/docs/18/runtime-config-resource.html#GUC-IO-METHOD) |
| Dragonfly | Redis/Memcached互換、LinuxのI/Oにio_uringを使用。比較条件が揃わない性能数字は掲載しない | [architecture](https://www.dragonflydb.io/guides/redis-and-dragonfly-architecture-comparison)、[SSD tiering](https://www.dragonflydb.io/blog/dragonfly-ssd-data-tiering-community-announcement) |
| Node.js / libuv | 一部ファイルI/Oで1.45から採用、1.49以降は既定をthreadpoolに戻した経緯。すべてのNode I/Oがio_uringを使用するとは言わず、rollback原因を速度と断定しない | [libuv fs](https://docs.libuv.org/en/v1.x/fs.html) |
| syscall / fd | fdはプロセスの番号表。socket/pipeも対象。raw syscallの戻り値はerrnoをエンコードし、writeは部分成功もある。完全例はエラー・短い書き込みを扱う | [syscalls](https://man7.org/linux/man-pages/man2/syscalls.2.html)、[read](https://man7.org/linux/man-pages/man2/read.2.html)、[write](https://man7.org/linux/man-pages/man2/write.2.html) |
| blocking | 待つスレッドがCPUを使い続けるとは説明しない。EAGAINは即時の結果でPromise pendingと同一ではない | [read](https://man7.org/linux/man-pages/man2/read.2.html) |
| epoll / io_uring | readinessを受けてアプリがreadする流れと、readを依頼してcompletionを受ける流れを比較。io_uringにもpoll機能があるため完全に排他的とはしない | [epoll](https://man7.org/linux/man-pages/man7/epoll.7.html)、[io_uring](https://man7.org/linux/man-pages/man7/io_uring.7.html) |
| 性能 | バッチ、共有リング、登録バッファ等で手間を減らせる可能性。syscall不要・必ず高速という断言を避ける。物理I/Oや小規模処理では利点が限定され得る | [io_uring_enter](https://man7.org/linux/man-pages/man2/io_uring_enter.2.html)、[register](https://man7.org/linux/man-pages/man2/io_uring_register.2.html)、[kernel FUSE](https://kernel.org/doc/html/latest/filesystems/fuse/fuse-io-uring.html) |
| 運用 | Docker公式資料の既定seccompプロファイルはio_uring関連syscallをブロック。Engine・プロファイルで異なり、EPERMは別の原因でも発生する | [Docker seccomp](https://docs.docker.com/engine/security/seccomp/)、[setup](https://man7.org/linux/man-pages/man2/io_uring_setup.2.html) |

出典URLは各ページの発表者ノートと最終参考資料にも記載した。PostgreSQLの発表だけではCPU・SSD・クエリの詳細条件を再現できないため、比較ベンチマークとして掲載していない。

## Zig 0.17.0の確認

[公式一覧](https://ziglang.org/download/index.json)の2026-10-01リリースと[リリースノート](https://ziglang.org/download/0.17.0/release-notes.html)を確認。公式ソースアーカイブのSHA256は`b6c7f1728f043700d6529bac980800792f824256a9d2f1839b3d62beed0b8abd`。同梱の`lib/std/Io.zig`、`Io/Uring.zig`、`os/linux.zig`、`os/linux/IoUring.zig`をインストール済み0.17.0と照合した。

- `std.Io`は操作と実装を分離するインターフェース。既定の`std.process.Init.io`はThreaded。
- `Io.Evented`はOSとfiber対応状況に応じた選択。LinuxではUring、macOSではDispatch。Threaded / Evented / Uringを独立した3実装として描かない。非対応targetではvoidになる。
- `Io/Uring.zig`のlisten / accept / connectはUnavailable経由でNetworkDown。process操作等にもTODO panicがあり、全バックエンドの同等性・完成度は保証しない。
- `std.os.linux.IoUring`は低レベルのリング操作APIで、`std.Io.Uring`バックエンドとは別。
- `std.Io.failing`は標準で提供される。`std.testing.io`も存在するが、汎用Mockとして任意動作を再現するものではない。
- `async`は逐次実行へfallbackできる。`concurrent`は並行実行を提供できなければConcurrencyUnavailable。Futureのawait/cancelは関数の戻り値型を保つ。cancelは強制停止ではない。

本編のDI例は、同じ`app(io)`へThreadedとfailingを渡してstdoutへの出力の成功・失敗を実測したもの。これでepollとUringの性能比較やUring内部の検証ができたとは説明していない。

## コード実測

`orb -m zig-syscall-lab`、Fedora aarch64、Linux `7.0.14-orbstack-00380-ga7e0a2dc9535`、Zig 0.17.0で`npm run check:linux`成功。[機械可読の記録](validation-linux.json)。

- raw_write：stdout `hello\n`。strace `write(1, "hello\n", 6) = 6`。
- raw_read：通常入力、300 byte入力、EOFを読み取り、同じ内容を出力。
- io_basic：std.Io経由で`hello\n`。
- io_injection：Threadedで成功、failingで`error.InputOutput`。どちらも同じapp関数。
- io_uring_read：低レベルリングで/dev/zeroから128 byte。CQE `user_data=42, res=128`、内容もゼロと検査。

`check:snippets`：本文Zig抜粋3件と完全例5件をx86_64-linux / aarch64-linux両方でコンパイル、JS 1件を構文確認。本文のコードは抜粋と明記し、完全例をsnippets/に用意した。

`zig test tests/future_contract.zig`：逐次fallback、ConcurrencyUnavailable、エラー共用体保存の3テスト成功。await/cancelの再取得も確認。ただしこれはUringの非同期キャンセル実測ではない。

## 表示とビルド

`npm install`、`npm run build`、`npm run export`成功。macOSではビルドまで、Linux VMではプラットフォーム専用の依存関係を/tmp/zig-lt-slidevに導入し、システムのChromium headlessでPDF出力。Noto Sans CJK JPを使用。

全23ページのPDFをPNGにして目視。コード背景はダーク、本文は白黒。説明・図・コードの色相を統一。性能説明と限界のページは本文と末尾メッセージの余白を調整。自動表示確認は`npm run check:visual`で再実行でき、スクリーンショットは既定で/tmp/zig-lt-visualに出力する。

## 未検証・改善候補

- epoll対io_uringの制御された性能測定。PostgreSQLの最大3倍を両方式の比較値に使わない。
- Docker内のseccomp拒否の実測。図は公式資料に基づく拒否例であり、今回のVM直接実行は成功した。
- Uringバックエンドのネットワーク対応APIと非同期キャンセル競合の検証。
- 発表練習で15分への調整。ノートの秒数は目安。

## 追加：std.Ioバックエンド差し替えデモ

`snippets/io_backend_demo.zig`と`snippets/build.zig`、`snippets/README.md`を追加。共通のapp()はHello, World!と改行を出力するだけ。初期化と後始末を呼び出し側へ分離し、ビルド時にThreaded / Eventedを選ぶ。epoll比較直後に設計と実測の2ページを追加し、既存のstd.Io紹介は対応状況の説明へ変更した。

公式0.17.0のThreadedでは実行成功。straceで`writev(1, [{iov_base="Hello, World!\n", iov_len=14}], 1) = 14`を観測。EventedではIo/Uring.zig:759のprocessReplacePathがIo.VTableに存在せず、コンパイル失敗。インストール済みLinux版とmacOS版のIo.zig / Io/Uring.zigは同じハッシュで、公式配布ソースにも同じフィールド指定がある。

一時コピーでの調査ではprocessSpawnPath、inheritParentDir / inheritParentFileにも不整合が見つかった。インストール済み標準ライブラリは変更していない。パッチを当てたライブラリの実測として提示せず、Eventedのstdout一致・setup/enter観測は未完了と明記した。ソース内でリング初期化が行われることと、straceで実際に観測できたことを区別する。

[実測記録](validation-backends.json)のcomparisonCompleted=falseが今回の結論。`npm run check:backends`はビルド可否と成功した経路のみを記録し、Eventedのビルド失敗を隠さない。標準ライブラリの修正版で両経路を実行・比較することが今後の課題。Zigの優位性や性能の証拠として扱わない。

## 追加：poll / epoll比較実験

benchmarks/poll-epoll/にZig 0.17.0の実行可能ベンチマークを追加。std.os.linuxのpoll / epoll_wait（aarch64ではppoll / epoll_pwait）を使用し、Eventedには依存しない。readiness取得A、受信区間の予備測定、送信開始〜全受信完了のバースト型End-to-End Bを分けた。Producerも測定するBでは送信時間の割合も別記し、Aを併用して取得コストが隠れないようにした。

固定負荷は初回1280＋代表条件480＋送信込み640＋送信込み再測定240＋逆転再確認40本測定。各条件10回、warmup除外、ReleaseFast、方式順・条件順を乱択。全sampleでReady集合または受信byte数とデータ内容を検査。保存後の整合性はvalidate.pyで再確認できる。

低Ready率でepoll優位、高Ready率で差が縮小。予備系列では逆転がなかったが、送信込み4096fd/全Ready/1KiBで小さなpoll優位が2系列で出たためAdaptiveへ進んだ。モデルは独立校正crossover-checkのrun1..5から作り、動的評価後のチューニングはしない。EMA・最低継続・切替費用回収判定を含め、切替時はepollをclose/再登録してProducer側に隠れたepoll費用を残さない。

1%→100%→1%、各200ms、各方式10本測定の動的負荷はpoll0.312M、epoll1.076M、Adaptive1.074M msg/s。Adaptiveは中央値2回・2.130msの切替。対epollのペア改善率中央値-0.40%、95%区間-1.61〜+2.48%。改善も悪化も断定せず、今回の改善は確認できなかったと結論した。切替費用を無視したオフラインOracleのheld-out改善余地は約0.80%。

fd復習後・io_uring紹介前に3枚追加。取得時間とEnd-to-End msg/sのグラフを分離し、中央値・各10回・環境・条件を明記。poll青、epoll茶、Adaptive紫を統一。全23枚のノート目安は本編14分25秒＋操作余白35秒（発表練習は未実施）。

Linuxの3テストは0/全Ready、集合一致、LT再通知、部分消費、EAGAIN、データ後のEOF、解除、解放、実シグナルEINTRを確認。Adaptiveの最低継続テスト1件、動的評価全sampleのデータ整合性も確認。x86_64-linuxコンパイル成功。straceの時間は性能表へ混ぜない。
