import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from bridge.extension_runtime import Runtime, is_enabled, load_env_file

ROOT = Path(__file__).resolve().parent.parent


class ExtensionRuntimeUnitTest(unittest.TestCase):
    def test_manifest_setup_skill_and_update_contract(self):
        manifest = json.loads((ROOT / "xangi-extension.json").read_text(encoding="utf-8"))
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemaVersion"], 2)
        self.assertEqual(manifest["displayName"], "xangi-even-g2")
        self.assertEqual(manifest["version"], package["version"])
        self.assertEqual(manifest["runtime"], {"kind": "managed-http"})
        self.assertEqual(manifest["entrypoint"], "scripts/xangi-extension")
        self.assertEqual(manifest["deviceIngress"], {
            "capability": "device.even-g2", "authentication": "extension-bearer",
        })
        self.assertEqual(
            manifest["update"],
            {"prepare": {"command": "./scripts/prepare-update", "args": []}},
        )
        self.assertTrue((ROOT / manifest["setup"]["instructions"]).is_file())
        skill = ROOT / "skills" / "xs-xangi-even-g2" / "SKILL.md"
        self.assertTrue(skill.is_file())
        self.assertTrue(
            skill.read_text(encoding="utf-8").startswith(
                "---\nname: xs-xangi-even-g2\n"
            )
        )
        self.assertFalse((ROOT / "SKILL.md").exists())

    def test_load_env_file_preserves_process_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("EXISTING=file\nQUOTED='hello world'\n", encoding="utf-8")
            environ = {"EXISTING": "process"}
            load_env_file(env_file, environ)
        self.assertEqual(environ["EXISTING"], "process")
        self.assertEqual(environ["QUOTED"], "hello world")

    def test_enabled_values(self):
        self.assertTrue(is_enabled(None))
        self.assertTrue(is_enabled("yes"))
        self.assertFalse(is_enabled("false"))

    def test_child_stderr_is_persisted_and_appended_across_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "child.py"
            script.write_text("import sys; print('received bytes=32000', file=sys.stderr)\n")
            for _ in range(2):
                runtime = Runtime(root, root, {})
                child = runtime.start_logged_child("stt", script, dict(os.environ))
                self.assertEqual(child.wait(timeout=5), 0)
                runtime.stop()
            log = root / ".xangi/logs/xangi-even-g2/stt.log"
            self.assertEqual(log.read_text().count("received bytes=32000"), 2)
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_startup_waits_for_model_not_device_or_bridge(self):
        runtime = Runtime(ROOT, ROOT, {})
        runtime.stt = Mock()
        runtime.stt.poll.return_value = None
        runtime.bridge = None
        with patch("bridge.extension_runtime.probe_json", side_effect=[None, {"ok": True}]):
            health = runtime.health()
        self.assertFalse(health["ready"])
        self.assertEqual(health["startup"], {"state": "complete"})
        with patch("bridge.extension_runtime.probe_json", return_value=None):
            self.assertEqual(runtime.health()["startup"], {"state": "complete"})

    def test_startup_failure_is_terminal(self):
        runtime = Runtime(ROOT, ROOT, {})
        runtime.stt = Mock()
        runtime.stt.poll.return_value = None
        with patch("bridge.extension_runtime.probe_json", return_value=None):
            self.assertEqual(runtime.health()["startup"], {"state": "initializing"})
        runtime.stt.poll.return_value = 1
        with patch("bridge.extension_runtime.probe_json", return_value=None):
            self.assertEqual(runtime.health()["startup"], {"state": "failed"})

    def test_disabled_stt_does_not_hold_initialization_group(self):
        runtime = Runtime(ROOT, ROOT, {"EVEN_EXTENSION_STT_ENABLED": "false"})
        with patch("bridge.extension_runtime.probe_json", return_value=None):
            health = runtime.health()
        self.assertFalse(health["ready"])
        self.assertEqual(health["startup"], {"state": "complete"})

    def test_requires_token_for_non_loopback_bridge(self):
        runtime = Runtime(
            ROOT,
            ROOT,
            {
                "EVEN_BRIDGE_HOST": "0.0.0.0",
                "EVEN_BRIDGE_TOKEN": "",
                "EVEN_EXTENSION_STT_ENABLED": "false",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "EVEN_BRIDGE_TOKEN is required"):
            runtime.start()


class ExtensionRuntimeSmokeTest(unittest.TestCase):
    def test_managed_runtime_reports_bridge_health_and_stops_with_parent(self):
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            bridge_port = reserved.getsockname()[1]

        token = "managed-test-token"
        env = dict(os.environ)
        env.update(
            {
                "XANGI_EXTENSION_AUTH_TOKEN": token,
                "EVEN_EXTENSION_STT_ENABLED": "false",
                "EVEN_BRIDGE_HOST": "127.0.0.1",
                "EVEN_BRIDGE_PORT": str(bridge_port),
                "EVEN_BRIDGE_TOKEN": "bridge-test-token",
            }
        )
        process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "bridge" / "extension_runtime.py"),
                "serve",
                "--workspace",
                str(ROOT),
            ],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            ready = process.stdout.readline()
            self.assertIn('"event": "ready"', ready)
            base_url = json.loads(ready)["baseUrl"]
            self.assertNotEqual(base_url, f"http://127.0.0.1:{bridge_port}")
            with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                urllib.request.urlopen(f"{base_url}/health", timeout=1)
            self.assertEqual(unauthorized.exception.code, 401)
            request = urllib.request.Request(
                f"{base_url}/health",
                headers={"Authorization": f"Bearer {token}"},
            )
            health = {}
            for _ in range(30):
                try:
                    with urllib.request.urlopen(request, timeout=1) as response:
                        health = json.loads(response.read())
                    if health["ready"]:
                        break
                except urllib.error.URLError:
                    pass
                __import__("time").sleep(0.1)
            self.assertTrue(health["ready"])
            self.assertFalse(health["stt"]["enabled"])
            self.assertEqual(health["bridge"]["host"], "127.0.0.1")
            self.assertNotEqual(health["bridge"]["port"], bridge_port)
            for headers in ({}, {"X-Xangi-Device-Authorization": "Bearer wrong"}):
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(urllib.request.Request(
                        f"{base_url}/device/health", headers={"Authorization": f"Bearer {token}", **headers}
                    ), timeout=2)
                self.assertEqual(rejected.exception.code, 401)
            with urllib.request.urlopen(urllib.request.Request(
                f"{base_url}/device/health", headers={
                    "Authorization": f"Bearer {token}",
                    "X-Xangi-Device-Authorization": "Bearer bridge-test-token",
                }
            ), timeout=2) as response:
                self.assertTrue(json.loads(response.read())["ok"])
            self.assertIsNone(health["stt"]["port"])
        finally:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=5)
            stderr = process.stderr.read() if process.stderr else ""
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
            self.assertEqual(process.returncode, 0, stderr)


class SharedPortIntegrationTest(unittest.TestCase):
    def test_managed_children_audio_events_and_shutdown(self):
        class Host(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                body = b"data: ready\n\n"
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        host = ThreadingHTTPServer(("127.0.0.1", 0), Host)
        threading.Thread(target=host.serve_forever, daemon=True).start()
        self.addCleanup(host.server_close)
        self.addCleanup(host.shutdown)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bridge = root / "bridge"
            bridge.mkdir()
            for name in ("extension_runtime.py", "even_g2_bridge.py", "managed_listener.py"):
                shutil.copyfile(ROOT / "bridge" / name, bridge / name)
            (bridge / "stt_server.py").write_text('''import json
from http.server import BaseHTTPRequestHandler
from managed_listener import create_server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self): self.send({"ok": True, "model": "stub", "device": "cpu"})
    def do_POST(self):
        pcm = self.rfile.read(int(self.headers["Content-Length"]))
        self.send({"text": "bytes=" + pcm.hex()})
create_server("127.0.0.1", 0, Handler).serve_forever()
''')
            env = dict(os.environ, XANGI_EXTENSION_AUTH_TOKEN="runtime-secret",
                       EVEN_BRIDGE_TOKEN="device-secret", EVEN_EXTENSION_STT_ENABLED="true",
                       EVEN_BRIDGE_HOST="0.0.0.0", EVEN_BRIDGE_PORT="8791", EVEN_STT_PORT="8792",
                       XANGI_EXTENSION_HOST_URL=f"http://127.0.0.1:{host.server_port}")
            process = subprocess.Popen([sys.executable, str(bridge / "extension_runtime.py"), "serve", "--workspace", str(root)],
                                       env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            ports = []
            try:
                ready = json.loads(process.stdout.readline())
                base = ready["baseUrl"]
                def request(path, data=None, device="device-secret"):
                    return urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers={
                        "Authorization": "Bearer runtime-secret",
                        "X-Xangi-Device-Authorization": f"Bearer {device}" if device else "",
                    }), timeout=3)
                for _ in range(50):
                    with request("/health") as response:
                        health = json.loads(response.read())
                    if health["ready"]:
                        break
                    time.sleep(.05)
                self.assertTrue(health["ready"])
                ports = [health[key]["port"] for key in ("bridge", "stt")]
                self.assertEqual(len(set(ports)), 2)
                self.assertNotIn(8791, ports)
                self.assertNotIn(8792, ports)
                self.assertEqual(health["stt"]["host"], "127.0.0.1")
                with request("/device/stt", b"\x00\xff\x80\x13") as response:
                    self.assertEqual(json.loads(response.read()), {"text": "bytes=00ff8013"})
                with request("/device/terminal/events?thread_id=test&token=device-secret", device="") as response:
                    self.assertEqual(response.readline(), b"data: ready\n")
                for path in ("/device/health?token=device-secret", "/device/terminal/events?token=wrong"):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request(path, device="")
                    self.assertEqual(error.exception.code, 401)
            finally:
                process.stdin.close()
                process.wait(timeout=5)
                stderr = process.stderr.read()
                process.stdout.close()
                process.stderr.close()
                self.assertEqual(process.returncode, 0, stderr)
            for port in ports:
                with socket.socket() as client:
                    self.assertNotEqual(client.connect_ex(("127.0.0.1", port)), 0)
            self.assertNotIn("device-secret", (root / ".xangi/logs/xangi-even-g2/bridge.log").read_text())


if __name__ == "__main__":
    unittest.main()
