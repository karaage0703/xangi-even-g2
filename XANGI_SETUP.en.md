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
5. For a Managed Extension, set Bridge URL to the short HTTPS URL described below. The internal upstream is `http://<xangi-host>:<xangi-port>/api/devices/xangi-even-g2`. The xangi host must support this ingress. Keep the dedicated `EVEN_BRIDGE_TOKEN` (`DEVICE_BRIDGE_TOKEN` is also accepted). Bridge and STT bind automatically allocated loopback ports; configured HOST/PORT values apply only to standalone operation. Do not enter internal ports in the companion.

Stop old PM2 processes after verifying migration. Existing port 8791 URLs must be changed to the shared ingress.

Set `EVEN_EXTENSION_STT_ENABLED=false` to run only the bridge and use an
external speech-to-text endpoint or command.

## Connect using a short HTTPS URL (recommended)

Connect your iPhone and the computer running xangi to the same Tailscale private network (tailnet). This setup allows access only from devices permitted by that network; it does not publish xangi on the internet. Keep Tailscale on while using G2. The G2 connection also requires your dedicated token.

### Set up the xangi computer

The commands below assume xangi runs locally at `http://127.0.0.1:18888`. If you use another port, replace `18888` throughout.

**If you already open xangi over HTTP from another device, this changes its address to HTTPS.** Update bookmarks, iPhone Shortcuts and integration URLs too. If Tailscale is already configured on this computer, check the migration notes below before running the commands.

```bash
tailscale serve --bg --https=18888 http://127.0.0.1:18888
tailscale serve --bg --https=18888 --set-path=/eveng2 http://127.0.0.1:18888/api/devices/xangi-even-g2
```

### Set up the iPhone

Use the hostname printed by the commands above. In the companion app, save the following **Bridge URL** and your dedicated token:

```text
https://<your-machine>.<your-tailnet>.ts.net:18888/eveng2
```

Open xangi itself at the same URL without `/eveng2`. Use the hostname, not the `100.x.x.x` IP address, because the HTTPS certificate is issued for that hostname. Confirm that the G2 session list appears. Keep your token private.

<details>
<summary>Migration notes for an existing Tailscale setup</summary>

Save and inspect `tailscale serve status --json` before changing an existing setup. If port 18888 has a `TCPForward` to `127.0.0.1:18888`, run `tailscale serve --tcp=18888 off` before the two setup commands above. Remote access is briefly unavailable during the switch. Local loopback HTTP remains unchanged.

If port 18888 belongs to another service or is publicly exposed using Tailscale Funnel, do not overwrite it with these commands. Review that configuration first. Tailscale cannot give different paths on the same port different public/private exposure scopes. Other ports do not need changes for this setup.

If you previously configured a separate G2 port or public G2 route, remove only that old route after confirming the new URL works. For an authentication check, G2 requests without a token should return HTTP 401. See [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) for configuration details.

</details>

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

## Logs

Managed bridge/STT logs are stored under the workspace at `.xangi/logs/xangi-even-g2/bridge.log` and `stt.log`, each with a 5 MiB limit and three backups. They record audio receipt, transcription completion and HTTP response writes, without transcript text. A successful response write does not confirm display on G2.

Set the model with `EVEN_STT_MODEL` in `bridge/.env`. A variable inherited from the parent process takes precedence. Restart the Even G2 extension to apply a model change.
