# 原典・入手状況・再構成の範囲

確認日：2026-10-19。作業開始時main：`ddd78fd`。本ディレクトリのC/Zigは独自に作成した**再構成実験**であり、Michael Kerrisk氏の`altio/altio_speed.c`ではない。

## 講義資料

- [Linux/UNIX System Programming: epoll](https://man7.org/training/download/lusp_epoll_slides-mkerrisk-man7.org.pdf)
- 取得版：January 2026、revision `d49d0b54be95`、21 PDFページ、©2026 Michael Kerrisk。
- SHA-256：`e691d99157d2d091623e3c274f0dae4dd53fd85b6890639dce920aabf092d4e0`
- 参照：PDF物理17ページ（24-33/34）、18ページ（24-35/36）、21ページ（24-41/42）。PDF版の日付から過去の測定日時を推定しない。
- PDF本体は再配布しない。数値は`results/historical.csv`へ参考値として転記し、今回の実測とは別系列にする。

## オリジナルCソースの探索

[TLPI公式source index](https://man7.org/tlpi/code/index.html)が案内する[配布版tlpi-260523-dist.tar.gz](https://man7.org/tlpi/code/download/tlpi-260523-dist.tar.gz)を取得・展開した。

- 配布版SHA-256：`7bb1155f6a90f382e18eaf961133d4f3b0583afd278416fba97406bdb0c606e2`
- `altio/`には`t_select.c`、`self_pipe.c`、`select_mq.c`、`poll_pipes.c`、`multithread_epoll_wait.c`、`epoll_input.c`、`epoll_flags_fork.c`、`demo_sigio.c`とMakefileがあった。
- `altio_speed.c`は含まれなかった。完全なarchiveのファイル名検索でも検出されなかった。book版`tlpi-260523-book.tar.gz`も確認したが同様に含まれなかった（SHA-256 `698a09c7ff428d92e81d3a695a1d855955ebf328c4458b70d1d3d4541bc2fb65`）。
- 次の公開候補URLはHTTP 404：
  - `https://man7.org/tlpi/code/altio/altio_speed.c`
  - `https://man7.org/training/code/altio/altio_speed.c`
  - `https://man7.org/training/download/altio_speed.c`
- 完全一致のファイル名とGitHubを含むWeb検索でも、入手可能な元ソースは見つからなかった。これは本調査範囲での入手不能を意味し、元ソースが存在しないという主張ではない。

公式配布のBUILDINGには依存ライブラリの導入後にmakeする手順があるが、今回の配布には対象プログラムがなく、オリジナルの無改変ビルド・実行はできなかった。

## ライセンス

公式indexではTLPIの多くの例がGPLv3、ライブラリがLGPLv3であり、個別ファイルの表示を確認するよう案内されている。対象ファイルを入手できなかったので、そのファイル固有のライセンスを断定しない。

TLPIのCソース・ヘッダー・ライブラリは本実装へコピーしていない。公開された実験仕様から独立に作成した本ディレクトリのコードはMITとし、LICENSEを同梱する。講義資料の著作権を本実装のライセンスへ含めない。

## 確認できた仕様と未知の仕様

| 項目 | 講義資料で確認 | 今回の再構成 |
|---|---|---|
| fd | pipeまたはsocket | 主比較はpipe、socketpairを別対照 |
| fd配置 | dup2でread側を低位連続番号へ | read fd 3..N+2、writerは高位へ退避（開始番号3も仮定） |
| Ready | 事前にデータを投入、反復中は消費しない | 1 byte投入、全writerを保持、EOFを発生させない |
| 密度 | Ready対象をランダム配置 | 共通xorshift64/Fisher-Yates。元RNG・seedは不明 |
| sparse | 1個、配列の中間 | index floor(N/2) |
| 反復 | A/B/Cは100万回 | 同数を維持、warmupのみ短縮 |
| timeout | 未確認 | 主比較は-1という仮定。0を別対照 |
| maxevents | 未確認 | 主比較はNという仮定。1/16/64/R/Nを別対照 |
| イベント走査 | 厳密なループは未確認 | 主比較はAPIのみ＋件数検査。走査・集合照合は別対照 |
| 登録 | K件のDELとK件のADDを毎反復 | K件のペア、対象indexは反復に応じて循環（元の対象選択は不明） |
| 計時 | waitを繰り返すloopの時間 | MONOTONICでloop全体、登録・Ready生成・初回集合検証は外 |
| 元の機器/OS/最適化/反復sample数 | 未確認 | environment.jsonに今回の条件を保存 |

主比較のCとZigでは同じ仮定を採用する。推測を「原典と一致した仕様」と扱わない。

## 原典のコマンド表記

- 密度：`./altio_speed -f N -l 1000000 -w R mode`
- sparse：`./altio_speed -f N -l 1000000 -M mode`
- 更新：`./altio_speed -f 100 -l 1000000 -M -e K e`
- 位置の演習：`-f 1000 -l 100000 -x 999 p` と `-x 0 p`（selectでも比較）

本再構成のCLIはこれを模倣したものではなく、全条件を明示する独自の位置引数を使う。実コマンドは各raw行とscheduleに保存する。

## カーネル参照

上流stable v7.0.14（OrbStack独自patchは完全照合できていない）。コードは再配布せず、版と指紋を記録する。

- [fs/select.c](https://github.com/gregkh/linux/blob/v7.0.14/fs/select.c#L882)：SHA-256 `321a153b85522c64262f7af59c6daf7504da3374597816883a3935d9fe941dc8`。zero-timeout時の_qproc無効化、Ready検出後の無効化、全fd走査を確認。
- [fs/pipe.c](https://github.com/gregkh/linux/blob/v7.0.14/fs/pipe.c#L660)：SHA-256 `56251a2dd4baac01424132e2b96413b14d85d9ff13284146658be5d3c347b68c`。pipe_pollの通知先登録と状態確認を参照。

講義の仮説とカーネル参照は、一要因の対照実験と照合する。取得した上流コードが測定VMの全patchと一致するとは説明しない。

連続配置ではwriter iは2N+33+2iに保持される。通常配置との比較ではread fdの間隔だけでなく、writer番号やプロセスのfd table容量も変わり得る。「配置」という一要因の内部を、単一のcache効果へ分解した実験ではない。

## 再構成コードの版

主比較A/B/Cの凍結ソースは`results/main/source-snapshot/`。Cの索引はint32、Zigはusize64だったが、主比較の計時ループはAPIのみで、この索引配列を使うのは計時外の初回検証だけ。

対照を測る前に、Cの索引をsize_tへ揃え、両言語の事前取得結果検証にcompiler memory barrierを追加した。対照のソースは`controls-source-snapshot/`、指紋は`controls-source-hashes.json`と環境ファイルに保存する。原典コードの修正ではなく、独自再構成の公平性・最適化抑止の修正。条件・Ready生成・主比較の実行中バイナリは変えていない。source-revisions.jsonにも区別を記録した。

## 登録/投入の順序に関する追加監査

主比較はReadyにしてからADD、既存ベンチマークはADD後にReady化する。原典のこの順序は未確認。別planを固定して両順序を比較し、計時外の返却イベント列hashを独立実装で検査した。生成した両言語のソース・patch・SHAはresults/main/registration-sourceとregistration-environment.jsonに保存。元の主比較・対照snapshotや既存rawを置換していない。
