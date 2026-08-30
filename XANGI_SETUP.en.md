# xangi Extension setup

This repository can run the Even G2 bridge and local Whisper service as a
xangi-managed Extension.

## Set up the Extension

1. Create the Python environment:

   ```bash
   cd bridge
   uv sync
   cp .env.example .env
   ```

2. Edit `bridge/.env`. Keep `EVEN_BRIDGE_TOKEN` private. The managed runtime
   automatically uses the parent xangi Web URL, so `XANGI_BASE_URL` is only a
   fallback for standalone operation.
3. Register and start the Extension from the repository root:

   ```bash
   xangi extension link ./xangi-extension.json
   xangi extension start xangi-even-g2
   xangi extension status xangi-even-g2
   xangi extension doctor xangi-even-g2
   ```

   Do not treat `start` alone as readiness. Wait for `doctor` to report that
   both the bridge and STT are ready.
4. Verify with `xangi extension list` that `xangi-even-g2` is registered for
   autostart.
5. Keep the configured bridge URL in the Even Hub companion screen. The
   Extension owns the bridge process, but the G2 client still reaches its
   Tailnet-facing listener directly.

The previous PM2 bridge/STT processes and the Managed Extension cannot listen
on the same ports simultaneously. Stop the old processes and verify that the
ports are free before starting the Extension.

Set `EVEN_EXTENSION_STT_ENABLED=false` to run only the bridge and use an
external speech-to-text endpoint or command.

## Add or update the workspace skill

After initial setup or an Extension update, compare the bundled
`skills/xs-xangi-even-g2/SKILL.md` with the same-name skill in the workspace.

- Follow the workspace's existing layout, or propose `skills/xs-xangi-even-g2/` when none exists.
- Propose a change only for material API, operational, or failure-handling differences, and show the reason, target path, and summary first.
- Extension setup or update approval does not authorize workspace edits. Apply a minimal diff only after separate user approval.
- Keep the Extension source separate instead of cloning the entire repository directly under the workspace `skills/` directory.

## Updates

For a repository-managed Extension update, the manifest's `update.prepare`
runs `uv sync --frozen` against `bridge/uv.lock`. Recheck `status` and `doctor`
after the update, then propose any material bundled-skill changes separately.
