from __future__ import annotations

import hashlib
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "scripts" / "setup_toolchain.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "sdk-ci.yml"


class ToolchainSetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.work = ROOT / "build" / "test_toolchain_setup"
        shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)

    def test_incomplete_cached_toolchain_is_reinstalled(self) -> None:
        archive = self.work / "toolchain.zip"
        destination = self.work / "install"
        gcc = destination / "bin" / "mipsel-none-elf-gcc.exe"
        cc1 = destination / "libexec" / "gcc" / "mipsel-none-elf" / "15.2.0" / "cc1.exe"

        gcc.parent.mkdir(parents=True)
        gcc.write_bytes(b"cached gcc")
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("bin/mipsel-none-elf-gcc.exe", b"complete gcc")
            bundle.writestr(
                "libexec/gcc/mipsel-none-elf/15.2.0/cc1.exe",
                b"complete cc1",
            )

        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        command = [
            "pwsh",
            "-NoProfile",
            "-File",
            str(SETUP_SCRIPT),
            "-Archive",
            str(archive.relative_to(ROOT)),
            "-Destination",
            str(destination.relative_to(ROOT)),
            "-ExpectedSha256",
            digest,
        ]

        first = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Incomplete toolchain detected", first.stdout + first.stderr)
        self.assertIn("Toolchain ready", first.stdout)
        self.assertEqual(cc1.read_bytes(), b"complete cc1")

        second = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Toolchain already installed", second.stdout)

    def test_ci_caches_the_complete_toolchain(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("path: .toolchain", workflow)
        self.assertIn("mipsel-none-elf-15.2.0-8ba866e25c9826ee-full-v1", workflow)
        self.assertNotIn(".toolchain/bin\n", workflow)


if __name__ == "__main__":
    unittest.main()
