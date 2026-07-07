# xangi-even-g2 bridge

[Japanese README](README.md)

This directory contains the server side of `xangi for G2`.

- `even_g2_bridge.py`: HTTP bridge used by the Even Hub app
- `stt_server.py`: local Whisper STT server for G2 microphone PCM

The bridge talks to xangi. The STT server only transcribes audio.

## Python Environment

Python dependencies are managed with `uv`.

```bash
cd /path/to/xangi-even-g2/bridge
uv sync
```

`even_g2_bridge.py` uses only the Python standard library. `stt_server.py` uses `openai-whisper`, `torch`, and `numpy`.

## Configuration

```bash
cd /path/to/xangi-even-g2/bridge
cp .env.example .env
```

Edit `.env`:

```bash
EVEN_BRIDGE_HOST=0.0.0.0
EVEN_BRIDGE_PORT=8791
EVEN_BRIDGE_TOKEN=change-this-to-a-long-random-token
XANGI_BASE_URL=http://127.0.0.1:18888
EVEN_MAX_CHARS=400
EVEN_DISCORD_REPLY_TIMEOUT_SEC=1800

EVEN_STT_HOST=127.0.0.1
EVEN_STT_PORT=8792
EVEN_STT_MODEL=medium
EVEN_STT_LANG=ja
```

Important values:

- `XANGI_BASE_URL`: xangi Web URL that provides `/api/chat`
- `EVEN_BRIDGE_TOKEN`: Bearer token expected from the G2 app
- `EVEN_BRIDGE_HOST`: use `0.0.0.0` for Tailscale direct HTTP; `127.0.0.1` is enough when publishing with Tailscale Serve
- `EVEN_DISCORD_REPLY_TIMEOUT_SEC`: Max seconds to wait for the final xangi reply after a G2 post to a Discord session. The HTTP request returns first; the Discord reply is posted asynchronously.
- `EVEN_STT_MODEL`: `medium` is the recommended default for Japanese accuracy; use `base` if memory is tight

## Run Locally

Use two terminals.

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

Health checks:

```bash
curl http://127.0.0.1:8792/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
```

## Run With PM2

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
pm2 start uv --name even-g2-stt -- run stt_server.py
pm2 start uv --name even-g2-bridge -- run even_g2_bridge.py
pm2 save
```

Useful commands:

```bash
pm2 list
pm2 logs even-g2-bridge --nostream --lines 80
pm2 logs even-g2-stt --nostream --lines 80
pm2 restart even-g2-bridge --update-env
pm2 restart even-g2-stt --update-env
```

Avoid broad `pkill -f` patterns. Use PM2 commands or a specific PID.

## Tailscale Direct HTTP

This is the simplest private setup.

```bash
tailscale ip -4
```

Use this app Bridge URL:

```text
http://<tailscale-ip>:8791
```

For direct HTTP, keep:

```bash
EVEN_BRIDGE_HOST=0.0.0.0
```

Then confirm from another tailnet device:

```bash
curl -H "Authorization: Bearer <token>" http://<tailscale-ip>:8791/health
```

## Tailscale Serve

Use this when you want a private tailnet HTTPS URL.

The bridge can listen on `127.0.0.1` or `0.0.0.0`.

```bash
tailscale serve --bg 8791
tailscale serve status
```

Use this app Bridge URL:

```text
https://<machine>.<tailnet>.ts.net
```

Tailscale Serve is private to your tailnet. It is different from Funnel, which publishes to the public internet.

## iPhone Companion Settings

Save these values on the Even Hub iPhone companion screen:

- `Bridge URL`: Tailscale direct HTTP URL or Tailscale Serve HTTPS URL
- `Token`: `EVEN_BRIDGE_TOKEN`

These saved values are used by the app.

Use `pack:configured` only when you want a private build with the same URL/token prefilled. It is not required for normal use.

```bash
cd /path/to/xangi-even-g2
BRIDGE_URL=http://<tailscale-ip>:8791 \
BRIDGE_TOKEN=<token> \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```
