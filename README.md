# xangi for G2

[English README](README.en.md)

Even Realities G2 から xangi を使うための Even Hub アプリです。

このリポジトリには、G2 用アプリ、xangi へ接続する bridge、音声認識用のローカル Whisper STT サーバーが含まれます。基本方針は Store 配布ではなく、GitHub から取得して Tailscale 経由で個人の xangi に接続する構成です。

## できること

- G2 の表示で xangi の Web / Discord / Slack セッション一覧を見る
- G2 から新しい xangi Web セッションを作る
- G2 のマイク音声をタップ操作で録音する
- ローカル Whisper STT サーバーで音声を文字起こしする
- 文字起こし結果を送信前に確認する
- 選択中の xangi セッションへ投稿する
- xangi の応答と履歴を G2 に表示する
- companion 画面と G2 表示に build label を出して、インストールした版を確認する

## 構成

```text
Even G2
  -> Even Hub アプリ
  -> xangi-even-g2 bridge
  -> xangi Web API
  -> Discord / Slack / Web セッション

G2 マイク音声
  -> xangi-even-g2 bridge
  -> ローカル Whisper STT サーバー
  -> テキスト
```

bridge は薄い中継サーバーです。xangi 本体の改造は不要です。

## 推奨ネットワーク

個人利用では Tailscale を推奨します。

- xangi と bridge を動かすマシンを tailnet に参加させる
- Even Hub を動かす iPhone も同じ tailnet に参加させる
- G2 アプリは Tailscale IP、MagicDNS 名、または Tailscale Serve URL で bridge へ接続する
- Funnel は外部テスターに一時配布するときだけ使う

## セットアップ

詳しい手順は [docs/setup.md](docs/setup.md) を参照してください。

### xangi workspace の skill として使う

xangi workspace で使う場合は、既存の `skills/` ディレクトリへ移動して、このリポジトリを clone します。

```bash
cd /path/to/xangi-workspace/skills
git clone https://github.com/karaage0703/xangi-even-g2.git xangi-even-g2
```

clone 後、xangi に以下のように依頼できます。

```text
xangi-even-g2 スキルを使って、このマシンで Even G2 bridge / STT をセットアップして。Tailscale で iPhone から接続できるところまで確認して。
```

### 手動セットアップ

概要:

```bash
git clone https://github.com/karaage0703/xangi-even-g2.git
cd xangi-even-g2
npm install

cd bridge
cp .env.example .env
# XANGI_BASE_URL, EVEN_BRIDGE_TOKEN, EVEN_STT_MODEL などを設定
uv sync
```

bridge と STT サーバーを起動します。

```bash
cd bridge
set -a
. ./.env
set +a
uv run stt_server.py
uv run even_g2_bridge.py
```

常駐運用では PM2 を使います。詳細は [bridge/README.md](bridge/README.md) を参照してください。

## `.ehpk` の作成

通常の開発ビルドは Bridge URL / token を埋め込まずに package を作ります。

```bash
npm run pack
```

Bridge URL と token は、iPhone の companion 画面で入力して保存できます。

同じ URL/token を最初から入れた private build を作りたい場合だけ、`pack:configured` を使います。通常利用では必須ではありません。

```bash
BRIDGE_URL=http://100.x.y.z:8791 \
BRIDGE_TOKEN=your-token \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```

`pack:configured` は build env に URL/token を渡して package を作ります。URL/token は git には書き込まれません。通常は companion 画面で入力すれば足ります。

## Bridge URL の選び方

推奨順:

1. Tailscale Serve
   - 例: `https://your-host.your-tailnet.ts.net`
   - tailnet 内だけの HTTPS URL
2. Tailscale direct HTTP
   - 例: `http://100.x.y.z:8791`
   - シンプルで private
3. Tailscale Funnel
   - 例: `https://your-host.your-tailnet.ts.net/eveng2`
   - public HTTPS
   - tailnet 外のテスターに使う場合だけ

## アプリ設定

iPhone companion 画面で以下を保存できます。

- `Bridge URL`: 実行中の xangi-even-g2 bridge URL
- `Token`: `EVEN_BRIDGE_TOKEN`
- `Save`: companion WebView localStorage に保存
- `Clear`: 保存値を削除

ここで入力した値が使われます。

## 開発コマンド

```bash
npm run build
npm run pack
npm run pack:configured -- --bridge-url http://100.x.y.z:8791 --bridge-token your-token
npm run pack:check
```

配布前は以下の version を揃えます。

- `package.json`
- `package-lock.json`
- `app.json`
- `src/version.ts`

## リポジトリ構成

- `src/`: Even Hub アプリ本体
- `bridge/even_g2_bridge.py`: G2 アプリと xangi をつなぐ HTTP bridge
- `bridge/stt_server.py`: G2 マイク音声用のローカル Whisper STT サーバー
- `bridge/README.md`: bridge / STT / PM2 / Tailscale 運用
- `docs/setup.md`: xangi + Even G2 セットアップ手順（日本語）
- `docs/setup.en.md`: English setup guide
- `scripts/pack-configured.mjs`: Bridge URL/token の初期値を入れる private build helper

## ライセンス

MIT License です。詳細は [LICENSE](LICENSE) を参照してください。
