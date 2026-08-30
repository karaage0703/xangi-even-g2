# xangi for G2

[Japanese README](README.md)

Even Realities G2 glasses client for [xangi](https://github.com/karaage0703/xangi).

This repository contains the Even Hub app, a small xangi bridge, and a local
Whisper STT server. The recommended setup is private tailnet access with
Tailscale, the same style as a personal xangi deployment.

## What It Does

- Shows xangi Web / Discord / Slack sessions on the G2 display
- Creates a new xangi Web session from the glasses
- Records G2 microphone audio while holding, then stops on release
- Transcribes audio through a local Whisper server
- Shows the conversation first and automatically adds xangi-generated reply suggestions as an extra page after the latest reply
- Starts voice input on long press and shows the transcription confirmation on release
- Keeps tap-to-start / tap-to-stop as a compatible alternative
- Posts the transcribed text to the selected xangi session
- Shows xangi replies and session history on the glasses
- Shows the build label on both the iPhone companion screen and G2 display

## Architecture

```text
Even G2
  -> Even Hub app in this repo
  -> xangi-even-g2 bridge
  -> xangi Web API
  -> Discord / Slack / Web session

G2 microphone audio
  -> xangi-even-g2 bridge
  -> local Whisper STT server
  -> text
```

The bridge is intentionally thin. xangi itself is not modified.

The bridge and Whisper STT service can also run as a xangi Managed Extension
through `xangi-extension.json`. xangi then owns the child process lifecycle and
passes its Web URL to the bridge automatically. The G2 app currently continues
to connect directly to the bridge's Tailnet-facing listener. See
[XANGI_SETUP.en.md](XANGI_SETUP.en.md).

## Recommended Network Model

For personal use and GitHub-based distribution, use Tailscale.

- The machine running xangi and the bridge joins the tailnet
- The iPhone running Even Hub also joins the same tailnet
- The app connects to the bridge through a Tailscale IP, MagicDNS name, or
  Tailscale Serve URL
- No public Funnel endpoint is required

Funnel is only needed when the iPhone or tester is outside the tailnet. Store
distribution for arbitrary users is a separate problem and is not the current
target.

## Quick Start

See [docs/setup.en.md](docs/setup.en.md) for the full xangi + Even G2 setup.

### Use As A xangi Managed Extension

Clone the repository outside the xangi workspace and register it as a Managed Extension.

```bash
git clone https://github.com/karaage0703/xangi-even-g2.git
cd xangi-even-g2
cd bridge && uv sync --frozen && cp .env.example .env && cd ..
xangi extension link ./xangi-extension.json
xangi extension start xangi-even-g2
xangi extension doctor xangi-even-g2
```

The bundled AI skill lives at `skills/xs-xangi-even-g2/SKILL.md`. During setup,
compare it with the same-name workspace skill and add or update it only after
separate approval.

Then ask xangi:

```text
Use the xs-xangi-even-g2 skill to set up the Even G2 bridge and STT on this machine. Verify that the iPhone can connect through Tailscale.
```

### Manual Setup

Short version:

```bash
git clone https://github.com/karaage0703/xangi-even-g2.git
cd xangi-even-g2
npm install

cd bridge
cp .env.example .env
# Edit .env: XANGI_BASE_URL, EVEN_BRIDGE_TOKEN, EVEN_STT_MODEL
uv sync
```

Run the bridge and STT server:

```bash
cd bridge
set -a
. ./.env
set +a
uv run stt_server.py
uv run even_g2_bridge.py
```

Or run them with PM2 as described in [bridge/README.md](bridge/README.md).

For development, build a normal Even Hub package without embedding a Bridge URL or token:

```bash
npm run pack
```

Enter the Bridge URL and token on the iPhone companion screen.

Use `pack:configured` only when you want a private build with the same URL/token prefilled. It is not required for normal use.

```bash
BRIDGE_URL=http://100.x.y.z:8791 \
BRIDGE_TOKEN=your-token \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```

The generated `.ehpk` can be uploaded as an Even Hub beta/prototype build.

## Bridge URL Choices

Use one of these, in order of preference:

1. Tailscale Serve tailnet HTTPS
   - Example: `https://your-host.your-tailnet.ts.net`
   - Private to the tailnet
   - Good default when Even Hub wants HTTPS
2. Tailscale direct HTTP
   - Example: `http://100.x.y.z:8791`
   - Simple and private
3. Tailscale Funnel
   - Example: `https://your-host.your-tailnet.ts.net/eveng2`
   - Public HTTPS
   - Use only for testers outside your tailnet

## App Settings

The iPhone companion screen has `Bridge URL` and `Token` fields.

- `Bridge URL`: URL of your running xangi-even-g2 bridge
- `Token`: value of `EVEN_BRIDGE_TOKEN`; leave empty only if bridge auth is off
- `Save`: stores values in companion WebView localStorage
- `Clear`: removes saved values

These saved values are used by the app. Secrets are not written to git.

## Build Commands

```bash
npm run build
npm run pack
npm run pack:configured -- --bridge-url http://100.x.y.z:8791 --bridge-token your-token
npm run pack:check
```

Before distributing a build, keep these versions in sync:

- `package.json`
- `package-lock.json`
- `app.json`
- `src/version.ts`

The current build label is visible on the companion screen and G2 display. Use
it to verify that Even Hub installed the intended `.ehpk`.

## Repository Layout

- `src/`: Even Hub app source
- `bridge/even_g2_bridge.py`: HTTP bridge from the G2 app to xangi
- `bridge/stt_server.py`: local Whisper STT server
- `bridge/README.md`: bridge, STT, PM2, and Tailscale operation
- `docs/setup.md`: Japanese setup guide
- `docs/setup.en.md`: English setup guide
- `scripts/pack-configured.mjs`: private build helper that prefills bridge URL
  and token for private builds
- `SKILL.md`: agent skill instructions for operating this repository

## Current Scope

This project is optimized for GitHub-based installation by users who already
run xangi or are willing to run xangi locally. Public Store distribution is not
the main path yet.
