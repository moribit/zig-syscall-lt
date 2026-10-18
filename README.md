# Zigで見る非同期I/OとLinuxシステムコール

Webエンジニア向けのSlidevスライド（全15枚）。元資料のPDFをもとに、fd、read/write、blocking、epoll、io_uring、std.Ioの順で説明します。

## 起動

```sh
npm install
npm run dev
```

http://localhost:3030 を開きます。矢印キーまたはSpaceでページ送り、`p`で発表者モード、`o`で一覧表示です。各ページ末尾のHTMLコメントに発表者ノートがあります。

## 編集・ビルド

- `slides.md`: 本文、コード、発表者ノート
- `styles/index.css`: 共通の配色とレイアウト
- `global-bottom.vue`: ページ番号
- `setup/shiki.ts`: ダーク背景用シンタックスハイライトと、説明文に対応するコードの色

スライド背景・本文は白黒、コードブロックはダーク背景です。コード内は同じ色相の明るい色を使い、白背景の説明との対応とコントラストを保ちます。コードと対応する説明のみ、青（fd / io）、緑（バッファ）、紫（結果 / byte数 / Future）、茶（I/O操作 / async・await）を使っています。識別子や説明ラベルも併記し、色だけに依存しない構成です。

```sh
npm run build
npm run export
```

ビルド結果は`dist/`に出力します。PDF書き出しにはPlaywrightのChromiumが必要です。未導入の場合は`npm install -D playwright-chromium`を実行してください。

## 内容について

元資料: `/Users/mimoc/Downloads/zig_async_syscalls_lt_webfriendly.pdf`（全15ページ）。元資料の環境表記はZig 0.17 / Fedora on OrbStackです。

`std.Io`の説明は確認できたZig 0.16公式リリースノートに基づきます。0.17リリースノートは確認できなかったため、参考資料には掲載していません。0.16時点のEventedは実験段階、Uringは概念実証です。コードは説明用の抜粋であり、利用するZigバージョンのAPIを確認してください。実測やベンチマーク結果は含みません。
