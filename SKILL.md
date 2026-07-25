---
name: xangi-even-g2
description: Set up, build, package, deploy, and operate the Even Realities G2 client for xangi. Use for requests such as "set up xangi on G2", "build an EHPK", or "update the Even Hub beta".
---

# xangi-even-g2

Use this skill when working with the `xangi-even-g2` repository.

The default deployment model is GitHub clone, private Tailscale access, and an
Even Hub private or beta build. Do not assume Store distribution unless the
user explicitly asks for Store submission.

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
6. Build an `.ehpk`. Use `pack:configured` only when URL/token defaults are
   useful for private testing.
7. Install the `.ehpk` through the Even Hub private/beta flow.
8. Enter the Bridge URL and token in the iPhone companion screen when they are
   not preconfigured.

Use `docs/setup.md` as the canonical user-facing guide.

## Installing As A xangi Workspace Skill

For a xangi workspace, move to the existing `skills/` directory and clone the
public repository there:

```bash
cd /path/to/xangi-workspace/skills
git clone https://github.com/karaage0703/xangi-even-g2.git xangi-even-g2
```

After clone, the user can ask xangi to use this skill and set up bridge, STT,
and Tailscale.

## Build App

```bash
cd /path/to/xangi-even-g2
npm install
npm run build
npm run pack
```

The generated file is `xangi-even-g2.ehpk`.

## Configured Private Build

Use a configured build only when a private build should prefill the same Bridge
URL and token for repeated testing. The values can still be changed from the
iPhone companion screen.

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

Never expose or commit real bridge URLs or tokens. Treat a configured `.ehpk`
as a secret-bearing artifact.

## Version Check

Before distributing a build, keep these files in sync:

- `package.json`
- `package-lock.json`
- `app.json`
- `src/version.ts`

Verify them before packaging:

```bash
cd /path/to/xangi-even-g2
node - <<'NODE'
const fs = require('fs');
const pkg = require('./package.json').version;
const lock = require('./package-lock.json').version;
const app = require('./app.json').version;
const source = fs.readFileSync('src/version.ts', 'utf8')
  .match(/APP_VERSION\s*=\s*['"]([^'"]+)['"]/)[1];
console.log({ pkg, lock, app, source });
if (new Set([pkg, lock, app, source]).size !== 1) process.exit(1);
NODE
npm run build
```

The current build label is shown on the iPhone companion UI and the G2 session
list / terminal screen. Use it to verify that the intended build is installed.

## Update An Existing Even Hub Build

Uploading and changing distribution state are external actions. Perform them
only when the user explicitly asks to update Even Hub, publish a beta, or make
an equivalent distribution change. A request to build an `.ehpk` alone does not
authorize an upload.

Use the available authenticated browser or browser automation to open the Even
Hub Developer Portal:

```text
https://hub.evenrealities.com/
```

If authentication is required, let the user complete it in the browser. Do not
ask for account passwords or verification codes in chat.

Generic update flow:

1. Open the target project under `My projects`.
2. Record the current distributed build and its distribution channel.
3. Choose `Upload a build` and select the verified `.ehpk`.
4. Confirm the package name, package ID, version, and file size shown by the
   portal before submitting.
5. Add a concise changelog that describes this build rather than copying a
   release-specific template.
6. Create the build. New uploads may initially appear as private builds.
7. If the user requested beta distribution, promote the new build to Beta.
   Preserve the project's previous distribution scope unless the user
   explicitly requested a change.
8. Reload or re-read the project page and verify that the intended version is
   the active build in the intended channel.
9. Record the resulting state of both the new build and the previously active
   build. Portal behavior for older builds may change, so verify instead of
   assuming a fixed transition.

Store/Public submission is a separate workflow. Do not select Public, edit a
Store listing, or submit for review as part of a private/beta update unless the
user explicitly asks for it.

Report the observable result:

```text
Even Hub update complete.
- App: <project name>
- Version: <version>
- Distribution: <Private/Beta/Public and current status>
- Previous build: <version and observed status>
- Portal: <project URL>
- Device verification: <complete/not run>
```

### Secure Even Hub Login

Do not save an Even Hub password in `.env`, shell history, Git, or the browser
automation command line. Store it in the operating system's credential store
with `scripts/evenhub-credential.py`. The helper uses Python `keyring` to select
the native backend: Secret Service or KWallet on Linux, Keychain on macOS, and
Credential Locker on Windows. It contains no account-specific data.

For initial enrollment, use the helper's hidden terminal prompt. The command is
portable and does not print or log the password:

```bash
uv run scripts/evenhub-credential.py store --account '<email>'
```

On a Linux desktop, a GUI prompt may be piped directly to the same helper:

```bash
zenity --password --title='Even Hub login' \
  | uv run scripts/evenhub-credential.py store --account '<email>' --stdin
```

For later logins, retrieve the password only inside the process that fills the
authenticated browser. Do not pass the resolved value as a CLI argument or
include it in tool output. Remove it with `clear` if access should be revoked.
If no supported system keyring is available, stop and ask the user to configure
one; do not fall back to plaintext storage.

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

Use `EVEN_STT_MODEL=medium` by default, or `base` if memory is tight.

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
- `EVEN_BRIDGE_HOST`: `0.0.0.0` for Tailscale direct HTTP; `127.0.0.1` is
  enough when using Tailscale Serve
- `EVEN_STT_URL`: defaults to `http://127.0.0.1:8792/transcribe`

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

## Operation Checks

After a build or deployment change, verify:

```bash
npm run build
curl http://127.0.0.1:8792/health
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8791/health
```

On the glasses:

- Build label is current
- Session list appears and `+ New Session` is available
- Long text and long history can be navigated
- Recording shows transcription confirmation before sending
- AI reply suggestions can be opened, selected, and sent
- Discord posting, if used, posts through the configured xangi Discord bridge

## Common Failure Modes

- The private Bridge origin is missing from the package network whitelist:
  create a configured private build for that origin.
- The version was not bumped consistently: synchronize all four version files
  before packaging.
- The upload succeeded but remained private: verify and apply only the
  distribution state explicitly requested by the user.
- The portal UI changed: follow the current labels and verify the observed
  result instead of relying on fixed element positions.

## Documentation Rules

When updating public docs:

- Keep Tailscale as the main path.
- Keep Store submission as a future/secondary path.
- Do not include private tokens, Discord tokens, personal xangi URLs, or
  tailnet-only secrets.
- Prefer placeholders such as `http://100.x.y.z:8791`.

## Completion Checklist

- All four version sources match.
- `npm run build` and package creation succeed.
- No private URL, token, account identifier, or environment-specific browser
  command appears in public output or committed documentation.
- The final portal state is re-read after any upload or promotion.
- The resulting distribution scope matches the user's explicit request.
- Device verification is reported as complete or not run.
