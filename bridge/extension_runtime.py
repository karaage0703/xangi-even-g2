#!/usr/bin/env python3
"""Managed xangi Extension runtime for the Even G2 bridge and STT service."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


EXTENSION_ID = "xangi-even-g2"


def load_env_file(path: Path, environ: dict[str, str]) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key:
            environ.setdefault(key, value)


def is_enabled(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def probe_json(url: str, token: str = "", timeout: float = 0.4) -> dict | None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=timeout
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None


class Runtime:
    def __init__(self, repo_dir: Path, workspace: Path, environ: dict[str, str]):
        self.repo_dir = repo_dir
        self.workspace = workspace
        self.environ = environ
        self.bridge: subprocess.Popen[bytes] | None = None
        self.stt: subprocess.Popen[bytes] | None = None
        self.stt_enabled = is_enabled(environ.get("EVEN_EXTENSION_STT_ENABLED"))

    def start(self) -> None:
        bridge_dir = self.repo_dir / "bridge"
        child_env = dict(self.environ)
        bridge_host = child_env.get("EVEN_BRIDGE_HOST", "0.0.0.0")
        bridge_token = child_env.get("EVEN_BRIDGE_TOKEN", "").strip()
        if bridge_host not in {"127.0.0.1", "::1", "localhost"} and not bridge_token:
            raise RuntimeError(
                "EVEN_BRIDGE_TOKEN is required when the bridge listens beyond loopback"
            )
        host_url = child_env.get("XANGI_EXTENSION_HOST_URL", "").rstrip("/")
        if host_url:
            child_env["XANGI_BASE_URL"] = host_url
        self.bridge = subprocess.Popen(
            [sys.executable, str(bridge_dir / "even_g2_bridge.py")],
            cwd=bridge_dir,
            env=child_env,
            stdout=subprocess.DEVNULL,
        )
        if self.stt_enabled:
            self.stt = subprocess.Popen(
                [sys.executable, str(bridge_dir / "stt_server.py")],
                cwd=bridge_dir,
                env=child_env,
                stdout=subprocess.DEVNULL,
            )

    @staticmethod
    def _running(process: subprocess.Popen[bytes] | None) -> bool:
        return process is not None and process.poll() is None

    def health(self) -> dict:
        bridge_host = self.environ.get("EVEN_BRIDGE_HOST", "0.0.0.0")
        bridge_probe_host = "127.0.0.1" if bridge_host in {"0.0.0.0", "::", "*"} else bridge_host
        bridge_port = int(self.environ.get("EVEN_BRIDGE_PORT", "8791"))
        bridge_health = probe_json(
            f"http://{bridge_probe_host}:{bridge_port}/health",
            self.environ.get("EVEN_BRIDGE_TOKEN", ""),
        )
        stt_host = self.environ.get("EVEN_STT_HOST", "127.0.0.1")
        stt_probe_host = "127.0.0.1" if stt_host in {"0.0.0.0", "::", "*"} else stt_host
        stt_port = int(self.environ.get("EVEN_STT_PORT", "8792"))
        stt_health = (
            probe_json(f"http://{stt_probe_host}:{stt_port}/health")
            if self.stt_enabled
            else {"ok": True, "disabled": True}
        )
        bridge_ready = self._running(self.bridge) and bool(bridge_health and bridge_health.get("ok"))
        stt_ready = (
            not self.stt_enabled
            or (self._running(self.stt) and bool(stt_health and stt_health.get("ok")))
        )
        ready = bridge_ready and stt_ready
        return {
            "ok": ready,
            "ready": ready,
            "detail": "ready" if ready else "bridge or speech-to-text service is warming up",
            "bridge": {
                "running": self._running(self.bridge),
                "host": bridge_host,
                "port": bridge_port,
                "healthy": bridge_ready,
            },
            "stt": {
                "enabled": self.stt_enabled,
                "running": self._running(self.stt) if self.stt_enabled else False,
                "healthy": stt_ready,
                **(
                    {
                        "model": stt_health.get("model"),
                        "device": stt_health.get("device"),
                    }
                    if isinstance(stt_health, dict)
                    else {}
                ),
            },
        }

    def stop(self) -> None:
        for process in (self.stt, self.bridge):
            if process is not None and process.poll() is None:
                process.terminate()
        for process in (self.stt, self.bridge):
            if process is None or process.poll() is not None:
                continue
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def serve(workspace: Path) -> None:
    token = os.environ.get("XANGI_EXTENSION_AUTH_TOKEN", "").strip()
    if not token:
        raise RuntimeError("XANGI_EXTENSION_AUTH_TOKEN is required")

    repo_dir = Path(__file__).resolve().parent.parent
    child_env = dict(os.environ)
    load_env_file(repo_dir / "bridge" / ".env", child_env)
    runtime = Runtime(repo_dir, workspace.resolve(), child_env)
    runtime.start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.headers.get("Authorization", "") != f"Bearer {token}":
                self.send_error(401)
                return
            if self.path != "/health":
                self.send_error(404)
                return
            body = json.dumps(runtime.health(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    stopped = threading.Event()

    def shutdown() -> None:
        if stopped.is_set():
            return
        stopped.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, lambda *_: shutdown())
    signal.signal(signal.SIGINT, lambda *_: shutdown())

    def watch_parent() -> None:
        try:
            sys.stdin.buffer.read()
        finally:
            shutdown()

    threading.Thread(target=watch_parent, daemon=True).start()
    print(
        json.dumps(
            {
                "schemaVersion": 2,
                "event": "ready",
                "id": EXTENSION_ID,
                "baseUrl": f"http://127.0.0.1:{server.server_port}",
                "workspace": str(workspace.resolve()),
                "pid": os.getpid(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        runtime.stop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="xangi-even-g2-extension")
    parser.add_argument("action", choices=["serve"])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    serve(args.workspace)


if __name__ == "__main__":
    main()
