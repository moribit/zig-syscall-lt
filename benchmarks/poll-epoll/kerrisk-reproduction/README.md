# Kerrisk氏のI/O多重化ベンチマーク：公開仕様からの再構成

原典Cソースは公式公開配布で入手できなかったため、厳密なオリジナル再現ではない。[SOURCES.md](SOURCES.md)に探索先・SHA-256・確認できた条件と仮定を区別して記録した。[REPORT.md](REPORT.md)は実測結果と限界のレポート。

既存の`../results/`とAdaptive実装は変更しない。新しいraw、実行順序、環境、ソースsnapshot、CSV、SVGは本ディレクトリの`results/`へ保存する。過去の数値は`results/historical.csv`で今回の測定と分離する。

## 環境とビルド

Linux、Zig **0.17.0**、GCC、Python 3、matplotlib、tasksetが必要。今回の環境はM2 MacBook Air（hostの`sysctl`でApple M2確認）上のOrbStack/Fedora aarch64。CPU 2固定はVM内の指定であり、物理CPU専有や同一性能コアへの固定は保証しない。

```sh
# Fedoraで必要な場合（新しいVMを作る必要はない）
sudo dnf install gcc glibc-devel make python3-matplotlib strace
# リポジトリのルートから
zig version # 0.17.0
python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/test.py
python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/run.py --suite primary --output /tmp/kerrisk-new
python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/run.py --suite controls --output /tmp/kerrisk-new
python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/analyze.py /tmp/kerrisk-new
```

GCCは`-O2 -std=c11 -Wall -Wextra -Werror`、Zigは`-O ReleaseFast`。Cの最適化条件をZigと同一とみなさず、コンパイラの違いを含む比較として扱う。全ビルドコマンドとバージョンは環境JSONへ保存。ソースは無改変のオリジナルではなく、独立に作成した`c/reconstructed.c`と`zig/main.zig`。

```sh
gcc -O2 -std=c11 -Wall -Wextra -Werror benchmarks/poll-epoll/kerrisk-reproduction/c/reconstructed.c -o /tmp/kerrisk-c
zig build-exe -O ReleaseFast benchmarks/poll-epoll/kerrisk-reproduction/zig/main.zig -femit-bin=/tmp/kerrisk-zig
# backend kind N ready loops timeout capacity placement layout work changes seed
/tmp/kerrisk-c poll pipe 1000 100 1000000 -1 1000 random contiguous api 0 17
/tmp/kerrisk-zig poll pipe 1000 100 1000000 -1 1000 random contiguous api 0 17
```

runnerはCPU 2の利用可否、fd上限、Linux/Zigバージョンを確認する。fd上限は最低5,000を要求し、1,000組の両端を退避する一時fdにも余裕を持たせる。利用できない環境では理由を示して停止する。既存rawへの追記・上書き・失敗sampleの黙った除外はしない。測定を並列に実行しない。

## 測定条件

`results/main/plan.json`が計時前に固定した全条件。すべての条件と言語で2,000反復のwarmupを先に完了してから本測定する。同じrun/seedのCとZigを組にし、条件と組内の実行順は事前seedでシャッフルする。

- A：N=100/1000、Ready率10/20/50/100%、select/poll/epoll。
- B：N=1/10/100/1000、Ready1個を中間へ、poll/epoll。
- C：N=100、Ready1個を中間へ、K=0/1/5/10件のDEL+ADDを各反復で行う。
- A/B/Cは**100万反復・各条件3回**。動作確認後、1,000 fdの一部条件で1回に数十秒を要するため、このsample数を本測定前に固定した。3回のbootstrap区間は情報が少なく、確認的な有意性の証拠とはしない。
- 対照は各5回。API/走査の経路は20,000反復、事前取得配列の走査・集合検証とctl-onlyは100,000反復。容量比較の単発APIは100,000回、全Ready集合取得は1,000集合。これらを原典100万回の実測値と同じ総時間で比較しない。

## 再構成した処理

両言語で、N本のpipe（対照はsocketpair）を作成。低位連続配置では全read/write fdを高位へ複製し、read側を3..N+2へ配置する。writerは高位で保持し、EOF/HUPを発生させない。Ready対象へ1 byteを投入し、その後は読み取らない。

Ready集合は共通のxorshift64とFisher-Yatesで作る。両言語のReady bitmap hash、fd範囲、結果件数を照合する。中間はindex floor(N/2)。元のRNG・seed、timeout、maxevents、結果走査の実装は未確認。

主比較はtimeout=-1、maxevents=N、API＋返却件数検査のみ。この3点は仮定。Readyが1個以上あるので待機は即時に戻る。0 Readyでtimeout=-1を指定すると計時前に拒否する。timeout=0は別対照。

selectでは毎回入力fd_setを復元し、nfds=maxfd+1を指定。FD_SETSIZE超過を拒否する。ZigのLinux層にselect用公開ラッパーがないため、同層の`syscall6(.pselect6, ...)`を使う。Cはglibcのselect/poll/epoll_wait、ZigはLinux APIラッパーであり、syscall境界までの処理は完全には同じでない。

### workの区間と単位

| work | 計時する処理 | 単位 |
|---|---|---|
| api | 待機API＋返却件数検査・checksum | wait call |
| scan | api＋返された配列から索引を作る | wait call |
| verify | scan＋Ready bitmapとの照合・重複検査 | wait call |
| scan-only | 事前取得した配列の索引変換、APIなし | prepared scan |
| verify-only | 事前取得した索引のReady集合照合、APIなし | prepared verification |
| full | 上限付きepollを繰り返し、全Ready fdを一度以上確認 | complete Ready set |
| ctl-only | K組のDEL+ADDのみ | mutation iteration |

登録変更ありの主比較Cは、apiの後にK組を実行する。対象は`(iteration*K+j)%N`で循環し、Ready対象も含み得る。この対象選択は元ソースを確認できていない。初期ADDは`setup_epoll_ns`へ分離し、定常ループ外とする。

各計時はCLOCK_MONOTONICでループ全体を囲む。CPU時間はgetrusage差分。初期化、Ready生成、返却集合全体の事前確認、JSON出力、リソース解放は計時外。数百ns区間を毎回時計で挟む測定ではなく、十分な回数をまとめて測る。走査・検証単体は別のキャッシュ状態のループなので、区間中央値を加減算して厳密な内訳にしない。

### maxevents

Ready1000個で容量1/16/64/1000を比較（Ready数とNが同じなので重複する設定を統合）。単発呼び出しは返すイベント数自体が違う。`full`はLTの再通知を利用し、重複を管理して1000個の異なる対象が得られるまで呼ぶ。容量がRを割り切らない場合は最後の呼び出しで重複が混じり、events_observedはRを超え得る。

これは新しい通信イベント1000件の受信ではない。異なる量の仕事の単発呼び出しを、同等の全Ready取得と扱わない。

## データと再生成

```sh
python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/analyze.py
```

- `primary.jsonl` / `controls.jsonl`：全runとwarmup。`duration_ns`はループ区間。`iterations`と`unit`を必ず併読する。
- 各行の`command`、`sequence`、`start_unix_ns` / `end_unix_ns`は実行コマンド・順序・プロセス開始終了の記録であり、duration_nsとは別。
- `ready_hash`：Ready bitmapの共通の64bit bitmap hash（FNV型の独自初期値）。実際の全集合照合も事前に実行する。
- `wait_calls`は正常に返った待機回数、`events_observed`はそこで返されたイベント数、`ctl_calls`は完了した登録変更回数。EINTRは内部で再試行するが、割り込まれた待機試行を別カウントしていない。setup/事前確認のsyscallは含まない。実際のsyscall列は別straceでも観察する。
- `checksum`：結果が利用されることを保証する集計。メッセージ数ではない。
- `summary.csv`：各条件の中央値・bootstrap区間・最小/最大・CPU時間・イベント数/単位。
- `analysis.json`：seed/runの対応検査、C/Zig費用比、poll/epoll費用比。名目95%区間はペアまたは条件内中央値のpercentile bootstrap 10,000回。外れ値は除かない。
- `*-environment.json`：実行日時、kernel/CPU/VM、affinity、コンパイラ、最適化、fd上限、Git SHA、ソース/バイナリ/plan SHA、CPU負荷。
- `source-snapshot/` / `controls-source-snapshot/`：各系列の測定時ソース。formatや変更は作業コピーへ行う。
- `density-*.svg` / `sparse.svg` / `ctl.svg` / `capacity.svg`：raw/参考CSVから再生成可能。

straceは性能測定の終了後に別実行する。tracer下の時間を通常のJSONLへ混ぜない。再構成実験を本番Webサーバの性能・言語の優劣・現行Linux全般の保証へ一般化しない。

参考ファイルだけを再取得して指紋を検証する場合：`python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/fetch-sources.py /tmp/kerrisk-references`。公開版が変わった場合にhashを黙って更新しない。

主比較の初版と対照用の索引幅・barrier修正版はSOURCES.mdとsource-revisions.jsonで区別する。主比較を当時のコードで再実行する場合は、保存済み`source-snapshot/c/reconstructed.c`と`source-snapshot/zig/main.zig`をビルドする。現行ソースでの新しい測定も、必ず新出力先へ保存する。

## 登録と投入の順序の追加対照

`results/registration-plan.json`を追加測定前に固定した。`scripts/registration.py`は、保存済み対照版ソースから「投入後ADD」「投入前ADD」の2版を生成し、それ以外を揃えて測る。通常の主比較コードは変更しない。全Readyの初回返却列hashは、前者では登録順、後者では投入順になることを独立したPython実装で検証した。

保存済み結果の再集計・レポート更新：

```sh
python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/registration_analysis.py
python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/report.py
```

`registration.jsonl`は各20,000反復×5回（warmupは2,000反復）、生成ソースとpatchは`registration-source/`、別環境メタデータと実行順は`registration-environment.json`。計時前の`preflight_order_hash`はイベント索引の返却順をhash化し、`ready_hash`は順序によらない集合を検証する。登録順の介入は計時外、差が残るのは定常Ready Listの順序などである。

新しく一式を再実行する場合は、`python3 benchmarks/poll-epoll/kerrisk-reproduction/scripts/registration.py --output /tmp/kerrisk-new`。`run.py --output`で作った対照版ソースsnapshotを含み、controlsの終了メタデータがある場所を指定する。再集計は`registration_analysis.py /tmp/kerrisk-new`。保存済みrawの上書き・自動resumeは行わない。初期ADDのsetup時間は本対照のbefore/afterでReady状態も違うため、定常waitの比較と混ぜない。

`verify-only`のrawのunit文字列は`prepared_scan`（事前取得区間の総称）で、`work=verify-only`により集合検証区間と判別する。READMEの表では意味を明確にするためprepared verificationと表記した。
