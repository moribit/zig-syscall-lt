# 測定前に固定する比較設計（2026-10-21）

## ゲートと比較可能性

Zig 0.17.0の実ファイルを調査してAPIを選ぶ。最小RECVの内容検証が成功し、必要opcodeをprobeし、正しさテストが成功してから性能測定する。liburing/libcリンクなし。SQ/CQのatomic・mmapは0.17.0のstd.os.linux.IoUringを利用する。std.Io.Eventedは使用しない。変更前の既存ファイルSHAをresults/existing-manifest.jsonへ保存し、既存rawとAdaptiveを変更しない。

## B：主比較（送信込み、単一Consumerスレッド）

poll+recv、epoll LT+recv、io_uring RECVを同じ系列で再測定する。既存workload.zigのsocketpair/fill/receiveを直接再利用し、同じseed・fd数・Ready数・payload・byte内容で比較する。Consumerへ将来のReady集合は渡さない。全N fdに最初に受信要求を投入し、完了したfdだけ再投入する。未到着要求はバースト間で保持し、毎回キャンセルしない。

各バーストはProducer開始→fill全送信→Consumer受信→内容検証→次回の再投入/flush完了まで。既存B同様、ProducerとConsumerは同じスレッドで順次実行する（実サーバの並行到着ではない）。メッセージ数とpayloadは共通プロトコルの終了条件として渡すが、Ready fdのidentityはConsumerへ教えない。各fd1バースト1メッセージ、最大1024Bの共通予算、部分受信は残りを再投入し、重複SQEはpending状態で禁止する。RECVの各fd専用bufferは終了CQEまで保持する。

バースト毎に集合の順列を1個回転する。Producerのみが使い、全方式で同じ変更を行う。受信対象を予知しないことを維持しながら再受信/別Ready集合を確認する。最後のバーストでは受信済fdを再投入せず、それ以外の未完了要求を測定外でキャンセルし、cancel CQEと対象の終端CQEを両方回収してからring/bufferを解放する。終了費用は別記し、初期化+定常+終了の合計も示す。

## A：POLL_ADDの通知契約

第4方式io_uring POLL_ADD oneshot+recvを同じバーストで測る。完了後に実recvと再投入を含む「通知→排出→再武装」のサイクルであり、既存Aの非消費LT繰り返し通知へ数値を直接追加しない。専用グラフと区分を使い、RECV方式との違いを説明する。multishotはbaselineへ入れない。

## C：バッチ/容量（主比較成功後の別系列）

RECVで投入1/8/32/最大（ring SQ容量）を比較する。各CQ回収後には端数も必ずflushし、満杯になるまで待って受信が停止することを避ける。CQ回収1/64件、SQ容量64/Nの別対照も行う。CQ容量は未完了/終了時の要求を収容できる2N以上の2冪とし、SQサイズとの違いを記録する。SQ満杯ではflushしてから確保する。SQ dropped/CQ overflowまたはoverflow backlog flagを検出したら失敗とする。

SQPOLL/registered files/provided buffers/multishotは任意拡張で、今回はベースラインとバッチ評価を優先する。専用kernel threadのCPUを測らずにSQPOLLが有利と結論しない。

## 条件・事前の実行順固定

N=64/256/1024/4096、Ready率1/10/50/100%、payload64/1024B。Ready個数はceil(N*pct/100)、実際の割合も保存する。32バースト/プロセス、各条件10回、方式を同一seedで対応付け、同一run/条件の方式順と条件順を固定seedでシャッフルする。全条件の短いwarmupを先に終える。ReleaseFast、同じCPU2 affinity。VM affinityは物理CPU専有を保証しない。

CはN1024/4096、Ready1/100%、payload1024B、batch1/8/32/最大、CQ回収1/64、SQ64/Nの一要因対照。重複するbaseline条件は統合し、条件リストと順序を性能測定前にplan.jsonへ保存する。評価結果を見て閾値等を調整しない。

## 時計・指標

ループ両端のMONOTONICとgetrusage、Producer/Consumer/投入/待機・CQ回収を分離する。区間計時の時計費用を含み、中央値を足し合わせて厳密に分解しない。内容検証はE2Eに含める。初期化内のsetup/mmap/配列buffer確保/初期要求投入、初回完了、終了CQEの排出と破棄を別記する。socket生成費用は共通workload_setupに分ける。初期化込みの指標はbackend_init+E2E+終了（socket生成を含む別指標も保存）。

プロセス内カウンタは対象loopのwait/recv/send/enter回数。これを全syscall数と混同しない。straceは独立した短い観測でsetup/teardownも含む全syscallと対象syscallを記録し、tracer下の時間を性能結果へ混ぜない。失敗条件はエラーとして終了し、0や欠損値を高速な測定点にしない。

全raw・環境・実行コマンド・ソース指紋を保存する。中央値、最小/最大、同seed/runのペア比と95%記述的bootstrap区間（10000回）を生成し、外れ値を除外しない。VM上の探索的合成負荷であり、一般のWebサーバやLinux全体の保証にはしない。
