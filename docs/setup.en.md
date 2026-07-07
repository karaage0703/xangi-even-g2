# xangi + Even G2 Setup

This guide sets up xangi for Even Realities G2 with a private Tailscale network.

The target is GitHub-based installation, not public Store distribution.

## 0. Overview

You need three running pieces:

- xangi Web API
- xangi-even-g2 bridge
- xangi-even-g2 STT server

The Even Hub app talks only to the bridge. The bridge talks to xangi and the
local STT server.

```text
iPhone + Even Hub + G2
  -> Tailscale URL
  -> bridge:8791
  -> xangi Web API

bridge:8791
  -> STT server:8792
  -> Whisper model
```

## 1. Requirements

- Even Realities G2
- iPhone with Even Realities / Even Hub
- A machine that runs xangi
- Tailscale on the machine and iPhone
- Node.js 18 or later
- Python 3
- PM2, recommended for long-running bridge/STT processes
- A working xangi Web endpoint with `/api/chat`

## 2. Clone

```bash
git clone https://github.com/karaage0703/xangi-even-g2.git
cd xangi-even-g2
npm install
```

If you use this repository as an agent skill, point the agent at `SKILL.md`.

## 3. Start xangi

Start your xangi instance first and confirm that the Web API is reachable from
the same machine as the bridge.

Example:

```bash
curl http://127.0.0.1:18888/api/health
```

The exact xangi port depends on your deployment. Use the URL that serves
`/api/chat`.

## 4. Configure Bridge And STT

```bash
cd bridge
cp .env.example .env
```

Edit `.env`.

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

Notes:

- `XANGI_BASE_URL` must be the xangi Web endpoint with `/api/chat`.
- `EVEN_BRIDGE_TOKEN` should be changed before exposing the bridge to your
  tailnet.
- `EVEN_HISTORY_MESSAGE_MAX_CHARS` is the per-message limit sent to G2 history.
  The app paginates it by measured pixels.
- `EVEN_STT_MODEL=medium` is a good default for Japanese accuracy. Use `base`
  if memory is tight.

## 5. Run With PM2

Start STT:

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
pm2 start uv --name even-g2-stt -- run stt_server.py
```

Start the bridge:

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
pm2 start uv --name even-g2-bridge -- run even_g2_bridge.py
pm2 save
```

Health checks:

```bash
curl http://127.0.0.1:8792/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
```

## 6. Choose A Tailscale URL

Use one of these.

### Option A: Tailscale Direct HTTP

This is the simplest private setup.

Find the machine's Tailscale IP:

```bash
tailscale ip -4
```

Bridge URL:

```text
http://<tailscale-ip>:8791
```

Example:

```text
http://100.x.y.z:8791
```

This requires `EVEN_BRIDGE_HOST=0.0.0.0` or a bind address reachable from the
Tailscale interface.

### Option B: Tailscale Serve

This keeps access private to the tailnet while giving you a tailnet HTTPS URL.

Run the bridge on localhost or `0.0.0.0`, then publish it to the tailnet:

```bash
tailscale serve --bg 8791
tailscale serve status
```

Bridge URL:

```text
https://<machine>.<tailnet>.ts.net
```

Use this when the app or environment behaves better with HTTPS.

### Option C: Tailscale Funnel

Use Funnel only for testers outside your tailnet.

Funnel exposes a public HTTPS URL, so keep `EVEN_BRIDGE_TOKEN` enabled.

## 7. Build The Even Hub Package

For normal development builds, create a package without embedding a Bridge URL or token.

```bash
cd /path/to/xangi-even-g2
npm run pack
```

Enter the Bridge URL and token on the Even Hub iPhone companion screen.

Use `pack:configured` only when you want a private build with the same URL/token prefilled. It is not required for normal use.

```bash
cd /path/to/xangi-even-g2
BRIDGE_URL=http://<tailscale-ip>:8791 \
BRIDGE_TOKEN=<token> \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```

For Tailscale Serve:

```bash
BRIDGE_URL=https://<machine>.<tailnet>.ts.net \
BRIDGE_TOKEN=<token> \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```

What `pack:configured` does:

- Runs `npm run build`
- Sets `VITE_BRIDGE_URL` and `VITE_BRIDGE_TOKEN` as build-time defaults
- Writes the `.ehpk`
- Does not commit the URL or token

## 8. Install On Even Hub

Use Even Hub beta/prototype installation flow.

The exact Even Hub UI can change, but the important checks are:

- The installed app is `xangi for G2`
- The displayed build label matches `src/version.ts`
- The companion screen shows the same build label
- The app can reach `/health` through the configured bridge

## 9. Use On G2

Controls:

- Session list
  - Up/down scroll: select session
  - Tap: open selected session
  - `+ New Session`: create a new Web session
  - Double tap: exit
- Session screen
  - Up/down scroll: move through history/pages
  - Tap: start recording
  - Tap again: stop recording and show transcription confirmation
  - Tap on confirmation: send
  - Double tap on confirmation: discard
  - Double tap on session screen: return to session list

Discord sessions are posted through the bridge using the configured xangi
Discord integration. Posts are labeled as coming from G2 because Discord bot
tokens cannot impersonate the human account.

## 10. Troubleshooting

Bridge is unreachable:

```bash
pm2 list
pm2 logs even-g2-bridge --nostream --lines 80
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
tailscale status
```

STT is slow or inaccurate:

```bash
pm2 logs even-g2-stt --nostream --lines 80
curl http://127.0.0.1:8792/health
```

Try `EVEN_STT_MODEL=medium` for accuracy or `base` for lower memory.

Even Hub installed an old build:

- Check the build label on the companion screen and G2 display
- Bump `package.json`, `package-lock.json`, `app.json`, and `src/version.ts`
- Re-run `npm run pack:configured`

If network access is suspected:

- Check bridge logs first. If the request reaches bridge, the app is reaching the bridge.
- Confirm the saved `Bridge URL` and token in the companion screen.
- Confirm Tailscale reachability from the iPhone.
