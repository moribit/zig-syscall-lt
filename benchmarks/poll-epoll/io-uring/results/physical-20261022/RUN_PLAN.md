# 実機追試の事前条件（2026-10-22）

直前のio_uring比較を対象とし、poll/epoll/RECV/POLL_ADDとbatch/CQ/SQの同じ条件を実機で再測定する。過去のKerrisk/Adaptive系列を再測定したとは扱わない。

- ユーザー指定の実機へ既存SSH設定で接続。隔離した/tmp作業ディレクトリで実行。
- physical Mac mini、Intel i7-3615QM、4core/8thread、EndeavourOS、Linux6.18.9-arch1-2、x86_64。systemd-detect-virt=none。
- 既存Zig0.17.0をPATHに追加。ReleaseFast/native、libcリンクなし。以前のVM系列と測定Zigソースは同じ。
- CPU2 affinity、SMT sibling=6。専有コアではなく、governor=schedutil、周波数/温度/他負荷は固定しない。
- soft fd上限をSSHセッション内だけ1024→16384へ上げる。hard上限524288とOS設定は変更しない。
- strace6.19はArch公式archiveからユーザー作業領域へ展開し、システム全体へインストールしない。性能測定後の独立観測のみ。
- Python/matplotlibはユーザー作業領域のvenv。測定と集計を重ねない。
- 主系列：N64/256/1024/4096、Ready1/10/50/100%、64/1024B、32bursts×各10回、全warmup先行、同じseed/実行順。1520本測定。
- batch64固定のSQ64/N対照80本も追試する。VM系列と混ぜず別raw/環境/CSV/SVGへ保存する。
- 最小RECV・正しさテストが失敗した場合、性能値を創作せず原因を報告する。seccomp等を自動で緩めない。

取得後はpreserved-results.jsonのSHAで過去の結果が保持されたことを確認する。CPU/architecture/kernel/コンパイラnative targetがVMと異なるため、差を仮想化の有無だけに帰属しない。

## 実行時の計画との差

Bashの`ulimit -n 16384`により、測定シェルではsoftだけでなくhardも16384となった。environment.jsonのfd_limit=[16384,16384]が実際の値である。OS設定と別SSHセッションの既定hard=524288は変更していない。全方式で同じ制限を適用し、全条件の処理が成功した。
