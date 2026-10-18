# Usage and Development

[日本語](usage.md) | [README](../README.en.md) | [Design](design.en.md)

## G2 Controls

Controls:

- Session list
  - Up/down scroll: select session
  - Discord sessions show regular channels as `#channel-name` and threads as `T: thread-name`
  - Tap: open selected session
  - `+ New Session`: open a draft (saved on the first send)
  - Double tap: exit
- Session screen
  - Up/down scroll: move through history/pages; adjacent history loads in batches of 30
  - Moving before the first page wraps to the latest page; moving after the final page wraps to the first page
  - Show xangi-generated reply suggestions as an extra page after the latest reply; fixed fallback suggestions are not shown
  - Long press: record while held
  - Release: stop recording and show transcription confirmation
  - Tap: start recording with the compatible tap workflow
  - Tap again: stop recording and show transcription confirmation
  - Tap on confirmation: send
  - Double tap on confirmation: discard
  - Double tap on the session screen: return to the session list

The selected session keeps its platform when G2 sends a message. A Discord
session continues the same Discord conversation through xangi remote input,
while a Web session continues the same Web session. Completed Discord replies are displayed first; history reconciliation follows without blocking the reply display.

After Discord send acceptance, the conversation view returns and displays the reply when it arrives. Slack and other platforms support history viewing only. New sessions are saved on the first send.

## Building an Even Hub Package

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

## App Settings

The iPhone companion screen has `Bridge URL` and `Token` fields.

- `Bridge URL`: URL of your running xangi-even-g2 bridge
- `Token`: value of `EVEN_BRIDGE_TOKEN`; leave empty only if bridge auth is off
- `Save`: stores values in companion WebView localStorage
- `Clear`: removes saved values

Saved settings are used by the app and synchronized through Even storage. Configured private packages contain the embedded token; do not publish them.

## Build Commands

```bash
npm ci
npm test
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

### Startup ordering

Supporting xangi hosts serialize initialization within the default gpu group. Set `"startup": null` in the host extensions.json record to disable grouping for CPU-only operation or disabled STT. Separate GPUs can use different exclusiveGroup labels; configure actual devices separately. After timeout, inspect host status for the owner and blocking reason.
