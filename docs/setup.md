# xangi + Even G2 セットアップ

[English setup guide](setup.en.md)

Even Realities G2 から xangi を使うためのセットアップ手順です。

Store 配布ではなく、GitHub から取得して Tailscale 経由で自分の xangi に接続する構成を前提にします。

## 0. 全体像

必要なものは3つです。

- xangi Web API
- xangi-even-g2 bridge
- xangi-even-g2 STT server

Even Hub アプリは bridge へ接続します。bridge は xangi とローカル STT server へ接続します。

```text
iPhone + Even Hub + G2
  -> Tailscale URL
  -> bridge:8791
  -> xangi Web API

bridge:8791
  -> STT server:8792
  -> Whisper model
```

## 1. 必要なもの

- Even Realities G2
- Even Realities / Even Hub を入れた iPhone
- xangi を動かすマシン
- マシンと iPhone の Tailscale
- Node.js 18 以上
- uv
- PM2
- `/api/chat` を提供する xangi Web endpoint

## 2. リポジトリを取得

通常利用は public repo を clone します。

```bash
git clone https://github.com/karaage0703/xangi-even-g2.git
cd xangi-even-g2
npm install
```

xangi workspace の skill として使う場合は、既存の `skills/` ディレクトリへ移動して clone します。

```bash
cd /path/to/xangi-workspace/skills
git clone https://github.com/karaage0703/xangi-even-g2.git xangi-even-g2
```

clone 後、xangi に以下のように依頼できます。

```text
xangi-even-g2 スキルを使って、このマシンで Even G2 bridge / STT をセットアップして。Tailscale で iPhone から接続できるところまで確認して。
```

## 3. xangi を起動

先に xangi を起動し、bridge を動かすマシンから xangi Web API に届くことを確認します。

例:

```bash
curl http://127.0.0.1:18888/api/health
```

実際の port は xangi の構成に合わせます。bridge の `XANGI_BASE_URL` には `/api/chat` を提供する base URL を設定します。

## 4. bridge / STT を設定

```bash
cd bridge
cp .env.example .env
```

`.env` を編集します。

```bash
EVEN_BRIDGE_HOST=0.0.0.0
EVEN_BRIDGE_PORT=8791
EVEN_BRIDGE_TOKEN=change-this-to-a-long-random-token
XANGI_BASE_URL=http://127.0.0.1:18888
EVEN_HISTORY_MESSAGE_MAX_CHARS=60000

EVEN_STT_HOST=127.0.0.1
EVEN_STT_PORT=8792
EVEN_STT_MODEL=medium
EVEN_STT_LANG=ja
```

設定の要点:

- `XANGI_BASE_URL`: xangi Web endpoint
- `EVEN_BRIDGE_TOKEN`: iPhone companion 画面に入力する token
- `EVEN_BRIDGE_HOST`: Tailscale direct HTTP なら `0.0.0.0`
- `EVEN_HISTORY_MESSAGE_MAX_CHARS`: G2 履歴へ渡す1メッセージ上限。アプリ側で pixel pagination して読めます
- `EVEN_STT_MODEL`: 日本語精度重視なら `medium`、軽さ重視なら `base`

依存関係を入れます。

```bash
uv sync
```

## 5. PM2 で常駐起動

STT server:

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
pm2 start uv --name even-g2-stt -- run stt_server.py
```

bridge:

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
pm2 start uv --name even-g2-bridge -- run even_g2_bridge.py
pm2 save
```

health check:

```bash
curl http://127.0.0.1:8792/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
```

## 6. iPhone から bridge へ届く URL を決める

推奨順は以下です。

### Option A: Tailscale direct HTTP

一番シンプルな private 構成です。

マシンの Tailscale IP を確認します。

```bash
tailscale ip -4
```

iPhone companion 画面の `Bridge URL` には以下を入れます。

```text
http://<tailscale-ip>:8791
```

例:

```text
http://100.x.y.z:8791
```

この方式では `EVEN_BRIDGE_HOST=0.0.0.0` が必要です。

### Option B: Tailscale Serve

tailnet 内だけで使える HTTPS URL にしたい場合はこちらです。

```bash
tailscale serve --bg 8791
tailscale serve status
```

iPhone companion 画面の `Bridge URL` には以下を入れます。

```text
https://<machine>.<tailnet>.ts.net
```

### Option C: Tailscale Funnel

tailnet 外のテスターに一時配布する場合だけ使います。

Funnel は public internet に出るので、`EVEN_BRIDGE_TOKEN` は必ず有効にしてください。

## 7. `.ehpk` を作る

通常は Bridge URL / token を埋め込まない package を作ります。

```bash
cd /path/to/xangi-even-g2
npm run pack
```

Bridge URL と token は、Even Hub の iPhone companion 画面で入力して保存します。

同じ URL/token を最初から入れた private build を作りたい場合だけ、`pack:configured` を使います。通常利用では必須ではありません。

```bash
cd /path/to/xangi-even-g2
BRIDGE_URL=http://<tailscale-ip>:8791 \
BRIDGE_TOKEN=<token> \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```

Tailscale Serve の場合:

```bash
BRIDGE_URL=https://<machine>.<tailnet>.ts.net \
BRIDGE_TOKEN=<token> \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```

`pack:configured` は URL/token を build env として渡して package を作ります。URL/token は git には書き込まれません。

## 8. Even Hub にインストール

Even Hub の beta / prototype install flow で `.ehpk` をインストールします。

確認ポイント:

- インストールしたアプリ名が `xangi for G2`
- companion 画面の build label が期待した版
- G2 側の表示にも同じ build label が出る
- companion 画面で `Bridge URL` と `Token` を保存できる

## 9. G2 で使う

セッション一覧:

- 上下スクロール: セッション選択
- タップ: 選択セッションを開く
- `+ New Session`: 新しい Web session を作る
- ダブルタップ: 終了

セッション画面:

- 上下スクロール: 履歴・ページ移動
- タップ: 録音開始
- もう一度タップ: 録音停止、文字起こし確認を表示
- 確認画面でタップ: 送信
- 確認画面でダブルタップ: 破棄
- セッション画面でダブルタップ: セッション一覧へ戻る

Discord セッションへ投稿する場合、投稿は xangi の Discord bridge 経由になります。Discord bot token では人間アカウントを impersonate できないため、G2 からの投稿だと分かる表示になります。

## 10. トラブルシュート

bridge に届かない:

```bash
pm2 list
pm2 logs even-g2-bridge --nostream --lines 80
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
tailscale status
```

STT が遅い・精度が低い:

```bash
pm2 logs even-g2-stt --nostream --lines 80
curl http://127.0.0.1:8792/health
```

精度優先なら `EVEN_STT_MODEL=medium`、メモリ優先なら `base` を試します。

古い build が入っている:

- companion 画面と G2 表示の build label を確認
- `package.json`、`package-lock.json`、`app.json`、`src/version.ts` の version を揃える
- `npm run pack` で package を作り直す
- Even Hub で入れ直す

セッション一覧が出ない:

- companion 画面の `Bridge URL` と `Token` を確認
- bridge ログに `/terminal/sessions` が来ているか確認
- bridge ログで 401 が出る場合は token 不一致
- bridge ログに何も来ない場合は Tailscale URL / iPhone の Tailscale 接続を確認
