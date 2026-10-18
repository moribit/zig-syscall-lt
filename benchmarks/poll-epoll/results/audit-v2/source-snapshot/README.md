# 測定時のソース

`environment.json`の`sources`と8ファイルすべてのSHA-256が一致する。測定後に追加したCLIガード・Controllerテストを除いた、実際に測定したソースを保存した。`model.zig`は保存済みの`results/adaptive/model.json`から生成した固定モデル。

Linux / Zig 0.17.0で、このディレクトリから再ビルドできる。

```sh
zig build-exe -O ReleaseFast main.zig -femit-bin=/tmp/measured-main
zig build-exe -O ReleaseFast probe.zig -femit-bin=/tmp/measured-probe
zig build-exe -O ReleaseFast --dep model -Mroot=adaptive.zig -Mmodel=model.zig -femit-bin=/tmp/measured-adaptive
```

`binary-sha256.json`は当時の測定バイナリ。バイナリ内のパス等でハッシュが変わり得るため、異なるディレクトリでのビルドに同一バイナリを要求しない。追加のconfirmation系列では再ビルドした最終mainを使用し、mainのソースはこのsnapshotと一致する。

記録用のソースは編集・formatせず、変更する場合は作業コピーを使用する。
