# xangi-even-g2 bridge

[English README](README.en.md)

Even Realities G2 アプリと xangi をつなぐサーバー群です。

- `even_g2_bridge.py`: Even Hub アプリから呼ばれる HTTP bridge
- `stt_server.py`: G2 マイク音声を文字起こしするローカル Whisper STT サーバー

bridge は xangi の Web API に中継します。STT サーバーは音声をテキストにするだけです。

## Python 環境

Python 依存は `uv` で管理します。

```bash
cd /path/to/xangi-even-g2/bridge
uv sync
```

`even_g2_bridge.py` は標準ライブラリだけで動きます。`stt_server.py` は `openai-whisper` / `torch` / `numpy` を使います。

## 設定

```bash
cd /path/to/xangi-even-g2/bridge
cp .env.example .env
```

`.env` を編集します。

```bash
EVEN_BRIDGE_HOST=0.0.0.0
EVEN_BRIDGE_PORT=8791
EVEN_BRIDGE_TOKEN=change-this-to-a-long-random-token
XANGI_BASE_URL=http://127.0.0.1:18888
EVEN_MAX_CHARS=400
EVEN_HISTORY_MESSAGE_MAX_CHARS=60000
EVEN_DISCORD_REPLY_TIMEOUT_SEC=1800
EVEN_DISCORD_REPLY_JOB_TTL_SEC=3600

EVEN_STT_HOST=127.0.0.1
EVEN_STT_PORT=8792
EVEN_STT_MODEL=medium
EVEN_STT_LANG=ja
```

主な値:

- `XANGI_BASE_URL`: `/api/chat` を提供する xangi Web URL
- `EVEN_BRIDGE_TOKEN`: G2 アプリから bridge へ送る Bearer token
- `EVEN_BRIDGE_HOST`: Tailscale direct HTTP なら `0.0.0.0`、Tailscale Serve で出すなら `127.0.0.1` でも可
- `EVEN_MAX_CHARS`: root互換の短文応答上限。通常の terminal 履歴表示には使いません
- `EVEN_HISTORY_MESSAGE_MAX_CHARS`: G2 履歴へ渡す1メッセージ上限。アプリ側で pixel pagination して読む前提です
- `EVEN_DISCORD_REPLY_TIMEOUT_SEC`: G2 から Discord セッションへ投稿した後、xangi の最終回答を待つ上限秒数。HTTP応答は先に返し、Discord返信は非同期で投稿します。
- `EVEN_DISCORD_REPLY_JOB_TTL_SEC`: 非同期 Discord 返信を G2 アプリが取得できる保持時間
- `EVEN_STT_MODEL`: 日本語精度優先なら `medium`、メモリを節約するなら `base`

## ローカル起動

ターミナルを 2 つ使います。

Terminal 1:

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
uv run stt_server.py
```

Terminal 2:

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
uv run even_g2_bridge.py
```

動作確認:

```bash
curl http://127.0.0.1:8792/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
```

## PM2 常駐

`uv run` を PM2 から起動します。

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
pm2 start uv --name even-g2-stt -- run stt_server.py
pm2 start uv --name even-g2-bridge -- run even_g2_bridge.py
pm2 save
```

よく使う確認コマンド:

```bash
pm2 list
pm2 logs even-g2-bridge --nostream --lines 80
pm2 logs even-g2-stt --nostream --lines 80
pm2 restart even-g2-bridge --update-env
pm2 restart even-g2-stt --update-env
```

広い `pkill -f` は避けてください。PM2 コマンドか、対象 PID を確認してから停止します。

## Tailscale direct HTTP

個人利用で一番シンプルな private 構成です。

```bash
tailscale ip -4
```

iPhone companion 画面の `Bridge URL` には以下を入れます。

```text
http://<tailscale-ip>:8791
```

direct HTTP の場合は bridge を tailnet から見えるようにします。

```bash
EVEN_BRIDGE_HOST=0.0.0.0
```

別の tailnet device から確認します。

```bash
curl -H "Authorization: Bearer <token>" http://<tailscale-ip>:8791/health
```

## Tailscale Serve

tailnet 内だけの HTTPS URL が欲しい場合に使います。

bridge は `127.0.0.1` または `0.0.0.0` で待ち受けます。

```bash
tailscale serve --bg 8791
tailscale serve status
```

iPhone companion 画面の `Bridge URL` には以下を入れます。

```text
https://<machine>.<tailnet>.ts.net
```

Tailscale Serve は tailnet 内だけに公開されます。Funnel は public internet へ出す別機能です。

## iPhone companion 設定

Even Hub アプリの iPhone companion 画面で以下を保存します。

- `Bridge URL`: Tailscale direct HTTP URL または Tailscale Serve HTTPS URL
- `Token`: `EVEN_BRIDGE_TOKEN`

ここで入力した値が使われます。

同じ URL/token を最初から入れた private build を作りたい場合だけ、`pack:configured` を使います。通常利用では必須ではありません。

```bash
cd /path/to/xangi-even-g2
BRIDGE_URL=http://<tailscale-ip>:8791 \
BRIDGE_TOKEN=<token> \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```
