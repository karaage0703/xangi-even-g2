---
name: xangi-even-g2
description: Set up, build, package, and operate the Even Realities G2 client for xangi, including the Even Hub app, xangi bridge, local Whisper STT server, and Tailscale-based private deployment.
---

# xangi-even-g2

Use this skill when working with the `xangi-even-g2` repository.

The default deployment model is GitHub clone + private Tailscale access. Do not
assume Store distribution unless the user explicitly asks for Store submission.

## Repository Layout

- `src/`: Even Hub app source
- `bridge/even_g2_bridge.py`: HTTP bridge from the G2 app to xangi
- `bridge/stt_server.py`: local Whisper STT server for G2 microphone audio
- `bridge/README.md`: bridge, STT, PM2, and Tailscale operation
- `docs/setup.md`: Japanese setup guide
- `docs/setup.en.md`: English setup guide
- `scripts/pack-configured.mjs`: configured `.ehpk` builder
- `app.json`: Even Hub app metadata and network permissions
- `xangi-even-g2.ehpk`: generated package, not committed

## Main Setup Path

For a normal user who already runs xangi:

1. Clone this repository.
2. Start xangi and identify the xangi Web URL that provides `/api/chat`.
3. Start `bridge/stt_server.py`.
4. Start `bridge/even_g2_bridge.py`.
5. Expose the bridge to the iPhone through Tailscale direct HTTP or Tailscale
   Serve.
6. For real device testing, build a normal `.ehpk`. Use `pack:configured` only
   when URL/token defaults are useful.
7. Install the `.ehpk` through Even Hub beta/prototype flow.
8. Enter Bridge URL and token in the iPhone companion screen.

Use `docs/setup.md` as the canonical user-facing guide.

## Installing As A xangi Workspace Skill

For a xangi workspace, clone the public repository into `skills/`:

```bash
cd /path/to/xangi-workspace
mkdir -p skills
git clone https://github.com/karaage0703/xangi-even-g2.git skills/xangi-even-g2
```

After clone, the user can ask xangi to use this skill and set up bridge / STT /
Tailscale.

## Build App

```bash
cd /path/to/xangi-even-g2
npm install
npm run build
npm run pack
```

The generated file is `xangi-even-g2.ehpk`.

## Configured Private Build

This is optional. Use it only when a private build should prefill the same
Bridge URL and token for repeated testing. The values can still be changed from
the iPhone companion screen.

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

Never commit real bridge URLs or tokens unless the user explicitly asks and the
values are safe to publish.

## Version Check

Before distributing a beta build, keep these files in sync:

- `package.json`
- `package-lock.json`
- `app.json`
- `src/version.ts`

The current build label is shown on:

- iPhone companion header/footer
- G2 session list / terminal screen

Use this to verify that Even Hub installed the intended `.ehpk`.

## Run STT

```bash
cd /path/to/xangi-even-g2/bridge
cp .env.example .env
set -a
. ./.env
set +a
uv sync
uv run stt_server.py
```

Recommended model:

```bash
EVEN_STT_MODEL=medium
```

Use `base` if memory is tight.

Health:

```bash
curl http://127.0.0.1:8792/health
```

## Run Bridge

```bash
cd /path/to/xangi-even-g2/bridge
cp .env.example .env
set -a
. ./.env
set +a
uv sync
uv run even_g2_bridge.py
```

Important env:

- `XANGI_BASE_URL`: xangi Web endpoint with `/api/chat`
- `EVEN_BRIDGE_TOKEN`: token sent by the app
- `EVEN_BRIDGE_HOST`: `0.0.0.0` for Tailscale direct HTTP, `127.0.0.1`
  is enough when using Tailscale Serve
- `EVEN_STT_URL`: defaults to `http://127.0.0.1:8792/transcribe`

Health:

```bash
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
```

## PM2

```bash
cd /path/to/xangi-even-g2/bridge
set -a
. ./.env
set +a
pm2 start uv --name even-g2-stt -- run stt_server.py
pm2 start uv --name even-g2-bridge -- run even_g2_bridge.py
pm2 save
```

Useful checks:

```bash
pm2 list
pm2 logs even-g2-bridge --nostream --lines 80
pm2 logs even-g2-stt --nostream --lines 80
```

Avoid `pkill -f`. Use PM2 or a specific PID.

## Tailscale URL Selection

Default recommendation:

- Use Tailscale direct HTTP for the simplest private setup:
  `http://<tailscale-ip>:8791`
- Use Tailscale Serve when HTTPS is preferable:
  `tailscale serve --bg 8791`
- Use Funnel only for testers outside the tailnet.

Store/general public distribution is out of scope unless explicitly requested.

## Operation Checks

After a build or deployment change, verify:

```bash
npm run build
curl http://127.0.0.1:8792/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
```

On the glasses:

- Build label is current
- Session list appears
- `+ New Session` is at the top
- Long text scrolls
- Recording shows transcription confirmation before sending
- Discord posting, if used, posts through the configured xangi Discord bridge

## Documentation Rules

When updating public docs:

- Keep Tailscale as the main path
- Keep Store submission as a future/secondary path
- Do not include private tokens, Discord tokens, personal xangi URLs, or
  tailnet-only secrets
- Prefer placeholders such as `http://100.x.y.z:8791`
