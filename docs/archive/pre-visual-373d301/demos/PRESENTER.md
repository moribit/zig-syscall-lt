# 当日の操作メモ（15分）

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

## 時間配分

| Slide | 内容 | 秒 | 累計 | リハーサル実測 |
|---|---|---:|---|---|
| 1 | 動機・タイトル | 15 | 0:15 | |
| 2 | async/awaitの下 | 35 | 0:50 | |
| 3 | Zig＋write実演 | 65 | 1:55 | |
| 4 | syscall境界 | 40 | 2:35 | |
| 5 | fd＋blocking実演 | 85 | 4:00 | |
| 6 | pollの図 | 35 | 4:35 | |
| 7 | poll実演・切り替え込み | 85 | 6:00 | |
| 8 | epollの図 | 35 | 6:35 | |
| 9 | epoll実演・切り替え込み | 90 | 8:05 | |
| 10 | SQ/CQ・4クリック | 55 | 9:00 | |
| 11 | io_uring実演・切り替え込み | 180 | 12:00 | |
| 12 | ReadyとCompletion | 45 | 12:45 | |
| 13 | 発見 | 35 | 13:20 | |
| 14 | まとめ | 30 | 13:50 | |
| 15 | 資料案内 | 10 | 14:00 | |
| 余白 | 操作遅延・トラブル | 60 | 15:00 | |

io_uringの3分：ソース60秒、通常実行40秒、trace40秒、説明と切り替え40秒。
自動実行で人間の読み上げ速度は検証できないので、リハーサル実測は発表者が記入する。

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
時間が押したらwriteとblockingのソース、pollの通常実行、epollのソースを省略する。
slide13は一言にする。io_uringの依頼→完了とslide12の対比は残す。

## 終了後

- [ ] プロセスが残っていない（通常はjoinと終了、timeout時もプロセス単位で停止）。
- [ ] 当日の検証ログとリハーサル実測を保存。
- [ ] 質疑で性能を聞かれたら、旧測定レポートは別条件の資料だと説明する。
