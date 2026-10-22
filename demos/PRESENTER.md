# 当日の操作メモ（20枚・理解優先）

## 開始前

- [ ] OrbStackの`zig-syscall-lab`を起動、AC電源・画面共有・ネットワーク状態を確認。
- [ ] Linux内でリポジトリへ移動し、Zig 0.17.0とstraceを確認。
- [ ] 新しい`DEMO_CHECK_OUTPUT`で`sh demos/check.sh`を実行（20回×5本）。
- [ ] ターミナルの文字を24px以上、幅110文字程度にする。ソース表示にbatを使う場合は動作を確認。
- [ ] 別ターミナルにこの手順を開く。スライドのPresenter Modeを確認。
- [ ] 下のコマンドを履歴へ入れ、実行済みの成功出力を手元に残す。
- [ ] タイマーを開始してリハーサル。**説明・画面切り替え込み**で実測欄を埋める。

```sh
orb -m zig-syscall-lab
cd /Users/mimoc/zig-syscall-lt
sh demos/run.sh 0 --source
sh demos/run.sh 0 --trace
sh demos/run.sh 1 --trace
sh demos/run.sh 2 --source
sh demos/run.sh 2 --trace
sh demos/run.sh 3 --source
sh demos/run.sh 3 --trace
sh demos/run.sh 4 --source
sh demos/run.sh 4
sh demos/run.sh 4 --trace
```

`--source`は任意。通常実行とtraceの重複で時間を使いすぎない。
長いファイルはmainの中心（pipe・登録・wait/read・SQE/CQE）を指し、timerやdeferは読み上げない。
batがなければ`--source`は通常のcat。エディタで開く場合も同じファイルを使用する。

## スライド順と話すポイント

15分前後は目安。デモを含む配分の合計目安は約17分で、操作遅延や質疑の余白は別に見込む。
初心者の理解を優先し、時間へ厳格に合わせるために説明を削らない。
ソースはターミナルで**全文を表示**し、指す箇所を絞る。人間の読み上げ・画面切り替え込みの所要を実測欄へ記入する。

| Slide | 話すポイント・操作 | 秒の目安 | リハーサル実測 |
|---|---|---:|---|
| 1 | hotoさんのLTから生まれた疑問を口頭で話す | 15 | |
| 2 | Runtimeの下にOSのI/O機構がある。経路は実装依存 | 35 | |
| 3 | Zigは観察の道具。`run.sh 0 --source` → `0 --trace` → slide4へ | 65 | |
| 4 | writeの引数と戻り値を、syscall境界の図へ対応付ける | 45 | |
| 5 | fdはプロセスの番号。`1 --source` → `1 --trace` → slide6へ | 85 | |
| 6 | blocking / EAGAIN / 多数fdの忙しい再確認、から問題を立てる | 40 | |
| 7 | pollの区切り。クリックなしで次へ | 5 | |
| 8 | fds一覧を毎回渡す。reventsでReadyを知り、その後read | 50 | |
| 9 | `2 --source` → `2 --trace`。Ready時点では未read → slide10へ | 85 | |
| 10 | epollの区切り。クリックなしで次へ | 5 | |
| 11 | create1/ADDは初期登録、waitは結果取得。監視集合はKernelに残る | 60 | |
| 12 | `3 --source` → `3 --trace`。ADD2件とwait/readを別々に指す → slide13へ | 90 | |
| 13 | io_uringの区切り。依頼の対象が状態から操作へ変わる | 5 | |
| 14 | 下の4クリック順でSQE・通知・CQE・user_dataを説明 | 80 | |
| 15 | `4 --source` → `4` → `4 --trace`。READ完了とbuffer → slide16へ | 180 | |
| 16 | ReadinessとCompletion。何が通知されたかを左右で振り返る | 45 | |
| 17 | poll/epoll/io_uringを同じ3段階＋helloで横比較する | 50 | |
| 18 | fd・待機API・操作/完了の3つの発見を言葉で確かめる | 35 | |
| 19 | 非同期処理の少し下を覗く楽しさで結ぶ | 30 | |
| 20 | デモと一次資料を案内する | 10 | |

表のコマンドはすべて `sh demos/run.sh` の引数。ターミナルにいる間は該当デモ開始スライドを残す。
io_uring実演の3分目安：ソース60秒、通常実行40秒、trace40秒、説明と切り替え40秒。

## 導入・図・コードの注目点

* **poll（7→8→9）**：監視したいfdの一覧を毎回渡す。`fds`と`revents`を指す。
  図は依頼→結果→readの順。Readyで戻ってもhelloはまだアプリに読まれていない。
* **epoll（10→11→12）**：監視集合を事前登録する。create1で作り、ADD2件。
  図の点線行が初期登録。その後のwaitへ監視fd一覧を渡し直す必要はない。
  `events`は結果を受け取る配列。今回LTであり、登録は毎回やり直さない。
* **io_uring（13→14→15）**：状態ではなくREAD操作を頼む。図の左右は他方式と同じ。
  SQ/CQは双方から見える共有領域。ユーザー空間でのリング操作とenter syscallを分ける。
  42はアプリが付けたuser_data。CQEの42が同じ依頼、res=5が読み取ったbyte数。

短いコードは**呼び出しの抜粋**。変数の準備・fd変換・エラー処理はターミナルの全文で確認する。
特にio_uringの抜粋は正常経路をtryで示すが、デモのsubmit/copy_cqeはpending bufferの寿命を守るため
失敗時にpanicする。架空のAPIや同一のエラー処理だとは説明しない。
writeの戻り値は正常なら書き込んだbyte数。raw syscallのエラー表現や短いI/Oの確認はデモ全文にある。

## クリック順（slide14のみ）

1. **SQE準備**：READとuser_data=42を共有SQに用意する。
2. **submit**：今回の実装はio_uring_enterでカーネルへ通知。pipeからREADを処理する。
3. **CQE**：共有CQへ42/res=5が返る。copy_cqeで回収する（必要ならenterで待つ）。
4. **対応確認**：同じ42の結果とbufferのhelloを確かめる。

区切り3枚にはアニメーションなし。他の概念図は固定表示。
デモ後のslide16は通知の意味、slide17は監視集合と操作の流れの違いを復習する。
io_uringにはPOLL_ADDもあるため、API全体が排他的な分類だとは説明しない。

## 見せる場所

* 0：writeの引数→straceの`write(1, "hello\\n", 6) = 6`。説明ログのstderrと区別。
* 1：read開始→約1秒待機→writerのwrite→readの復帰。fdはpipeの読み/書きで別。
* 2：空pipeのEAGAIN→fds配列を渡すppoll→Ready fd→その後read。
* 3：create→ADD2件→epoll_pwait→Ready fd→その後read。監視集合を保持。
* 4：ring初期化→READのSQE（42）→submit→CQE（42、5）→buffer hello。

結果を確認したらすぐ次のスライドへ。SQE/CQEのメモリアクセスはstraceに行として出ない。
`io_uring_register`は今回不要。性能の速い遅いの話に寄り道しない。

## 失敗・時間超過

10秒以内に切り上げ、「ここからは保存ログです」と伝える。

```sh
sh demos/run.sh 4 --saved
cat demos/recordings/validation-orbstack/04-io-uring.strace
```

番号を変えれば他のデモも同じ。**保存ログをライブ成功と説明しない**。
現場でパッケージ導入・権限設定変更・カーネル更新を始めない。
時間がかかった場合は、通常実行とtraceで同じ説明を繰り返しすぎない。
ソース全文の紹介、依頼と結果の対応、slide16・17の復習を優先し、理解を確かめながら進める。

## 終了後

- [ ] プロセスが残っていない（通常はjoinと終了、timeout時もプロセス単位で停止）。
- [ ] 当日の検証ログとリハーサル実測を保存。
- [ ] 質疑で性能を聞かれたら、旧測定レポートは別条件の資料だと説明する。
