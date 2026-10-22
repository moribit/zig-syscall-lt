# 継続到着実験：事前計画 v1

基準コミット: `d539bb5eeebb35f8c4a1d0d9da861daac6ba31c3`。性能データ取得前にコミットする。
過去の raw・図・Adaptive・Kerrisk再構成は変更しない。保護対象のハッシュは
`continuous/historical-sha256.json`。実装の修正履歴と性能測定開始時の SHA を記録する。

## 問い

H1: 長寿命接続では multishot が oneshot の再投入費用を減らせる。
H2: 継続到着では既存の送信後受信モデルと優劣が変わり得る。
H3: payload・接続数・アクティブ割合・到着率で性能差が変わる。
H4: batch は syscall を減らせるが CPU・遅延にトレードオフがある。
H5: 短い接続寿命・低負荷では初期化費用を回収できない場合がある。
反証も同じ形式で公開する。速さは正しさテストの合否に使わない。

## 共通プロトコルと計測窓

NONBLOCK Unix STREAM socketpair。Producer と Consumer は別スレッド。
固定長レコードのサイズが payload（ヘッダー込み）であり、先頭24Bは
接続別シーケンス番号・送信開始 MONOTONIC ns・接続index（各little-endian u64）、
残りは index と sequence から生成する決定的byte列。全byte・接続別順序を検証する。
部分受信・結合受信を共通パーサで処理する。Consumer は将来到着先を知らない。
送信時刻は最初の send の直前（部分送信の完了時刻ではない）。
遅延はこの時刻から完全レコード検証完了まで。全レコードで同じ時計取得・検証を行う。

開始バリア後、Producer は目標到着率に対する絶対時刻で送信する。
uniform は等間隔、randomized は固定seedの指数間隔、burst は32件ごとの集中到着。
開始時刻は全方式共通のプロトコル。終了時に全送信側を SHUT_WR し、Consumer は
EOF・全レコード検証まで drain する。計画件数、実送信、受信、drain時間を別記し、
未完了を切り捨てない。EAGAIN、送信開始の予定時刻超過、最大遅れを記録する。
Producer が遅れた場合、結果はConsumer単独の容量とは解釈しない。

## 比較実装

* epoll LT: 初回 ADD のみ。最大256イベント。1fdにつき64 KiBまで EAGAIN 排出。
* oneshot: 全接続に RECV を保持。完了後に再投入、SQ/CQはバッチ化。
* multishot: 全接続に multishot RECV、provided buffer ring。MORE が消えたら終端。
  BUFFER/BID と BUF_MORE を区別し、内容処理後にのみ buffer を返す。
  ENOBUFS は終端を確認して再投入。EOFまで buffer/request を保持する。

共通受信チャンク16 KiB、SQ256、CQ16384、provided buffer数4096（64 MiB）。
oneshot は接続ごとの16 KiBバッファ。buffer方針の差も比較対象の一部として明記する。
SQPOLL・fixed files・bundle は使わない。初期化・終了はsteady-stateと別計測。
baseline batch32/CQ256。追加 batch1/8/32/256 は別系列。
実装上必要な変更は性能結果を見る前に計画追記し、変更理由を残す。

## 正しさゲート

実機 Zig0.17.0 ReleaseFast。既存のringテストに加え、共通パーサの分割/結合/
破損/重複テスト、全方式の0/1/複数/全active、EOF、長時間処理、
multishot複数CQE/SQE、枯渇/終端/再投入、cancel終端、overflow検出を確認する。
未達のゲートがあれば探索結果を最終確認データと呼ばない。

## 環境と順序

最初は物理 i7-3615QM / Linux6.18.9 / Zig0.17.0。
Consumer CPU2、Producer CPU3（SMT兄弟はそれぞれ6/7）。物理CPU専有や周波数固定はしない。
soft fd上限16384。環境・負荷・日時・実行コマンド・順序・ソースSHAを保存。
OrbStack/M2は代表条件を別ディレクトリ・別集計で測り、混合しない。
straceは別実行、性能データに含めない。

## 探索の固定行列

全直積ではなく一要因スイープ＋相互作用の代表点。各条件3方式、warmup1回、本測定3回、
各窓0.5秒。順序は固定PRNG seed2026102201でランダム化。負荷は
10,000 / 50,000 / 200,000 / 1,000,000 messages/s（達成不能も記録）。
基準点256接続・10%active・256B・uniform・50,000/s。
そこから接続64/256/1024/4096、active1/10/50/100%、payload64/256/1024/4096、
pattern burst/uniform/randomized、到着率4水準を一軸ずつ変更、重複除去。
さらに全接続数×active割合をpayload1024B・uniform・200,000/sで評価。
この範囲を超えた一般化はしない。全測定・失敗・未達率を公開する。

## 指標・統計と独立確認

主指標: 完全検証messages/s、p50/p95/p99送信→完全復元遅延、
Consumer/Producer別CPU ms / million messages。窓内完了とdrain込み完了を区別する。
副指標: bytes/s、user/system CPU、初期化・終了ns、syscall/SQE/CQE/再投入/
recycle/EAGAIN数、送信遅れ、drain、overflow。
時計取得を空ループと比較する。中央値の区間値は加算しない。

探索後、multishot/epollのpaired throughput比で最大・1に最も近い・最小の条件と
基準点を選ぶ（重複除去、同率は条件キー昇順）。負荷達成率と遅延も併記し、
達成率95%未満の条件を「目標負荷をさばけた」と説明しない。
選択理由・全候補を `continuous/CONFIRMATION_PLAN.json` にコミットしてから、
新seed2026102301、20回、窓1秒、別順序で確認。paired ratio medianを10,000回
ペアbootstrap、95%区間。外れ値除去なし。探索による選択バイアスを明記。
区間が1を跨ぐ、または方向が再現しない場合、改善未確認。
CPUやp99を悪化させたthroughput改善は無条件の優位としない。

確認成功後に localhost TCP echo を独立系列へ拡張する。正しさ未達なら後続測定を停止し、
実測済み範囲と未完了事項を報告する。LTの更新は検証終了後、23枚・主要性能グラフ最大2枚。

## 一次資料

* 実機の Zig0.17.0 `lib/std/os/linux/IoUring.zig`（BufferGroup / setup_buf_ring）
* https://man7.org/linux/man-pages/man3/io_uring_prep_recv_multishot.3.html
* https://man7.org/linux/man-pages/man3/io_uring_setup_buf_ring.3.html
* https://man7.org/linux/man-pages/man7/epoll.7.html
