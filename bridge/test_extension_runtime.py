import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
