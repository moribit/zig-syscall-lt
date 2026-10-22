# 継続到着型io_uring比較：正しさ検証と停止原因

状態: **BLOCKED_CORRECTNESS**。探索・独立確認の性能データはまだない。
「io_uringが有利な条件を確認した」という結論は出していない。

## 1. 既存バースト型測定の限界

従来の `main.zig` は同一スレッドでProducerが送ってからConsumerが受信し、
32バーストの送信・検証・再投入を測定する。並行した継続到着、接続寿命全体、
メッセージごとの遅延は再現していない。既存の数値と新しいモデルを混ぜない。
既存epollは初回登録のみであり、不要なDEL/ADDをしていたわけではない。
新モデルでは複数レコードの排出と接続間の公平性を追加する。

基準mainは `d539bb5eeebb35f8c4a1d0d9da861daac6ba31c3`。
事前計画は結果取得前の `7b8f679` で公開した。
過去の実装・raw・図・レポートなど299ファイルのSHA-256は全件一致を確認した。

## 2. 到着モデルと環境

物理Mac mini（Macmini6,2）、Intel Core i7-3615QM、EndeavourOS、
`6.18.9-arch1-2`、x86_64、Zig **0.17.0 ReleaseFast**、libc/liburingなし。
Consumer CPU2、Producer CPU3（SMT兄弟6/7を避けた）、soft fd上限16384。
CPU専有・周波数固定なし。診断実行前の温度・周波数も保存した。
OrbStack測定は今回実施していない。

別スレッドProducerが固定seedで送信先と到着時刻を選ぶ。
uniform / 32件burst / 固定seed指数間隔のrandomizedを実装した。
Consumerには将来到着先を渡さない。固定長レコードはsequence・送信時刻・index・
検証用bodyを持ち、分割・結合を共通パーサで復元する。
最後の不完全なburstは計画送信件数で打ち切るよう修正した。

## 3. epoll LT

全fdを初期化時に一度登録。最大256イベント、16 KiB再利用buffer、
1fdあたり64 KiBを上限にEAGAINまで排出する。EOFでのみ登録解除する。
受信byte・sequence・全bodyを検証し、EOFで部分レコードが残っていないことも検査する。

## 4. oneshot RECV

全接続に保留RECVを用意し、完了した接続だけを再投入する。
将来のactive集合を使わない。接続ごと16 KiB buffer、SQ256、CQ16384。
CQから得たindexのリストだけを再投入し、毎回全N接続を走査しない。
EOF終端までbufferを保持する。

## 5. multishot RECV

全接続にmultishot RECVを投入する。CQE数とアプリケーションメッセージ数は別物。
`F_MORE`の消失を要求の終端とし、buffer取得・内容処理・返却後に必要な再投入を行う。
`ENOBUFS`も終端として扱う。SQ/CQ dropped/overflowはエラーで停止する。

小さなテストでは1 SQEから20回の送信を受け取れた。
ただし、これは後述する多接続EOF検証を通過したことを意味しない。

## 6. provided bufferと見つかった問題

実機の0.17.0 `IoUring.zig` の `BufferGroup` と公開buffer-ring関数を直接確認した。
標準 `BufferGroup.init` はincremental消費を要求する（非対応時は通常方式へfallback）。
最初のテストでは5 byte送信に対して4 byteのCQEを観測した。
buffer末尾で分割され得るため、テストをレコード全体の復元に修正した。
`F_BUF_MORE`と要求の`F_MORE`を区別し、bufferの残量追跡も標準実装へ委ねた。

継続到着検証では、incremental使用時にEOF待ちが停止した。
通常のprovided buffer（inc=false）で一度完走したが、繰り返すと同じ停止が発生した。
したがってincremental固有の問題とは結論しない。性能データを見る前の変更経緯は
[計画追記](CONTINUOUS_DESIGN.md)に残した。

## 7. 実機の再現結果

64接続、全active、64Bレコード、burst、目標10,000 messages/s、200ms、
2,000レコード。seed `2026102200` / `2026102201` / `2026102202`。
以下は**正しさの診断結果**であり、性能比較ではない。

| 方式 | 全レコード検証 | EOF確認数（3seed） | 完走 |
|---|---|---|---|
| epoll LT | 各2,000件 | 64 / 64 / 64 | 3/3 |
| oneshot RECV | 各2,000件 | 64 / 64 / 64 | 3/3 |
| multishot RECV | 各2,000件 | 61 / 63 / 60 | 0/3 |

multishotでは、watchdog時にpending接続の`recv(MSG_PEEK | MSG_DONTWAIT)`が0を返した。
socketはEOFを示す一方で、その要求の終端CQEが届いていない。
100ms timeout付き`io_uring_enter`で再度待機しても解消しなかった。
straceを付けた初期版の別実行は完走した。その版は最終burstを丸ごと送って
2,016件になるため、上表の2,000件と同一条件の性能比較には使えない。
straceによるタイミング変化も性能改善と扱わない。

根拠は `continuous/results/continuous-evidence-20261022/` 内の
`repeated/diagnostic.jsonl` と再生成可能な `correctness-summary.csv`。
初期系列はtimeout例外で停止しておりrawは成功した3行まで。
v2系列は失敗行とstderrもrawへ保存するようrunnerを修正した。
この違いを隠して両系列を完了データとして扱わない。

## 8. 上流のEOF競合との照合

[liburing issue #1549](https://github.com/axboe/liburing/issues/1549) はAF_UNIXの
multishot RECVで、別スレッドのsend直後のSHUT_WRによりEOF CQEが失われる再現を報告している。
[上流修正 a68ed2df7213](https://github.com/torvalds/linux/commit/a68ed2df72131447d131531a08fe4dfcf4fa4653)
は、データ到着とshutdownの通知がtask_work前に重なった場合、pollの参照処理で
終了状態の再確認が抜ける競合を修正する。

[stable v6.18.9のpoll.c](https://github.com/gregkh/linux/blob/v6.18.9/io_uring/poll.c)を確認し、
該当するHUP再試行処理がないことを照合した。ソースのblob SHAとSHA-256は
`continuous/kernel-source-audit.json` に保存した。

観測は既知の競合と整合する。ただし、稼働中Archカーネルのバイナリ解析や
修正済みカーネルへの切り替えによるA/B確認は行っていない。
したがって「この修正で必ず解決する」とは断定しない。
ZigのEventedコンパイル問題とも別であり、本件は直接Linux ABIを使った実行時の問題。

## 9. throughput / latency / CPU効率

**未測定**。診断ログの時間や単発の成功例から優位性を算出しない。
実装は全レコードlatency、window内完了件数、drain込み完了件数、
Producer/Consumer別THREAD CPUとprocess CPUを記録するが、
正しさゲート未達のため性能評価の証拠には使っていない。
時計取得オーバーヘッドの独立計測も未完了。

## 10. batch / 初期化 / 終了費用

SQE batch1/8/32/256のrunner、CQ256の回収、初期化・破棄時間の記録を実装した。
独立した性能測定は未実施。multishotのbuffer poolは4096×16 KiB、
oneshotはN×16 KiBであり、管理方式・メモリ量の差も比較の一部になる。
要求が残った正常終了を許さず、診断失敗時はabortする。
EOF検証を省略したり、Producerにsleepを足して競合を隠したりしない。

## 11. 有利・不利な条件と独立確認

今回の性能については**未確認**。
事前計画の探索31条件、3方式、warmup＋3回、および探索後の選択規則は固定した。
確認条件のファイルはまだ作っていない。探索データがないためである。
新seedによる20回の独立確認、paired bootstrap、全条件CSV/SVGの生成処理は追加したが、
実測系列を用いた検証は未実施。失敗系列から集計することは拒否する。

## 12. 正しさ・ビルド状況

* Zig 0.17.0 ReleaseFastビルド成功。
* 新規Zigテスト5件成功（root importを含む）：stream分割/結合/破損/重複、
  multishot複数CQEとrecycle/EOF、buffer枯渇後の再投入、cancelの終端確認。
* 0active・1fdは3方式とも完走。
* 多接続multishot EOFのゲートは失敗。長時間・全行列の正しさ検証は未完了。
* 保存済み299ファイルの保護ハッシュは全件一致。
* `npm run build`成功。スライド本文・グラフ・PDFは変更していない。

## 13. LTへの反映

指示どおり、検証完了前に性能グラフを更新しない。既存23枚を保持した。
PDF再出力・全ページ再確認も今回の変更としては未実施。
新しい結果の代わりに過去の成功値を流用していない。

## 14. 未実施項目

探索・独立確認・batch性能・OrbStack代表条件・TCP Echo・新SVG・性能CSV・
長時間安定性・時計オーバーヘッド・全エラー経路の網羅。
runnerのゲートは21シナリオを満たす同一Zigソースの完了系列を要求するが、
それだけで全故障注入項目を網羅した保証にはならない。
TCPは前段の確認成功後という条件を満たしていない。

## 15. 一般化と次の確認

これはUNSUPPORTEDなio_uring環境という意味ではない。setup・RECV・multishotの
データ受信は動作し、**この終了条件の正しさ検証が通らなかった**という結果である。
性能の勝敗も、全Linuxへの一般化もできない。
上流修正を含むカーネルで同じEOF検証を再実行することが次の確認になる。
今回、実機OS更新・カーネル更新・再起動・セキュリティ設定変更は行っていない。

## 16. 再実行

[continuous/README.md](continuous/README.md)のコマンドを参照。
正しさゲートが通過するまでrunnerは性能測定を拒否する。
既存結果は上書きせず、新しいディレクトリへ保存する。

一次資料:

* [multishot RECVの契約](https://man7.org/linux/man-pages/man3/io_uring_prep_recv_multishot.3.html)
* [provided buffer ring](https://man7.org/linux/man-pages/man3/io_uring_setup_buf_ring.3.html)
* [EOF wakeup raceの上流修正](https://github.com/torvalds/linux/commit/a68ed2df72131447d131531a08fe4dfcf4fa4653)
* [上流の再現報告](https://github.com/axboe/liburing/issues/1549)
