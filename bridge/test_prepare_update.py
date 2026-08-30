import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class PrepareUpdateTest(unittest.TestCase):
    def test_prepare_update_syncs_frozen_bridge_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            fake_uv = temp / "uv"
            capture = temp / "capture.txt"
            fake_uv.write_text(
                '#!/bin/sh\nprintf "%s\\n%s" "$PWD" "$*" > "$XANGI_TEST_CAPTURE"\n',
                encoding="utf-8",
            )
            fake_uv.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{temp}{os.pathsep}{os.environ.get('PATH', '')}",
                "XANGI_TEST_CAPTURE": str(capture),
            }
            subprocess.run(
                [ROOT / "scripts" / "prepare-update"],
                cwd=ROOT,
                env=env,
                check=True,
            )
            cwd, args = capture.read_text(encoding="utf-8").splitlines()
            self.assertEqual(Path(cwd), ROOT / "bridge")
            self.assertEqual(args, "sync --frozen")


if __name__ == "__main__":
    unittest.main()
