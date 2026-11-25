# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline protocol tests. Expected failures document open issues in the protocol."""
from ftplib import error_perm
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, expectedFailure, main, mock
import contextlib
import io
import os
import runpy
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
API = runpy.run_path(str(ROOT / "scripts/ps5-console.py"))
TITLE = "PPSA99871"


class MemoryFTP:
    def __init__(self):
        self.files = {}
        self.dropped = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def sendcmd(self, command):
        if command.startswith("DELE "):
            self.files.pop(command[5:], None)

    def size(self, name):
        return len(self.files[name])

    def storbinary(self, command, stream, **kwargs):
        self.files[command[5:]] = stream.read()

    def retrbinary(self, command, sink, **kwargs):
        if command[5:] not in self.files:
            raise error_perm("550 No such file")
        sink(self.files[command[5:]])

    def rename(self, source, target):
        if self.dropped:
            raise OSError("Simulated disconnect")
        self.files[target] = self.files.pop(source)


class ProtocolTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        source = self.root / TITLE
        (source / "sce_sys").mkdir(parents=True)
        (source / "sce_sys/param.json").write_text('{"titleId":"PPSA99871"}')
        (source / "eboot.bin").write_bytes(b"sample")
        (source / "asset").write_bytes(b"good")
        self.candidate = self.root / "frozen" / TITLE
        subprocess.run(["bash", ROOT / "scripts/freeze-candidate.sh", source,
                        self.candidate.parent], check=True, stdout=subprocess.DEVNULL)
        self.ftp = MemoryFTP()

    def cycle(self):
        env = dict(os.environ, PS5_HOST="127.0.0.1", PS5_FTP_PORT="1", PS5_LAUNCH="1",
                   PS5_LOCK=str(self.root / "lock"), PS5_LOCK_WAIT="0",
                   PS5_RESULTS=str(self.root / "logs"))
        return subprocess.run(["bash", ROOT / "scripts/ps5-cycle.sh", TITLE, self.candidate],
                              text=True, env=env, capture_output=True)

    def invoke(self, name, *args):
        fn = API["command_" + name]
        with mock.patch.dict(fn.__globals__, connect=lambda: self.ftp,
                             ensure_directory=lambda *args: None), contextlib.redirect_stdout(io.StringIO()):
            fn(args)

    def test_lock_owner_preserved(self):
        lock = self.root / "lock"
        lock.write_text("someone else")
        self.assertEqual(self.cycle().returncode, 3)
        self.assertEqual(lock.read_text(), "someone else")

    def test_changed_manifest_entry_stops_before_connect(self):
        (self.candidate / "asset").write_bytes(b"changed")
        proc = self.cycle()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("differs from its SHA256SUMS", proc.stdout)
        self.assertFalse((self.root / "lock").exists())

    def simulated_cycle(self, *, titles_error=False, after="running", app_log=None, logs=(), legacy=False):
        # Use the actual coordinator with inert transport and an isolated script directory.
        helpers = self.root / "helpers"
        helpers.mkdir()
        shutil.copy(ROOT / "scripts/ps5-cycle.sh", helpers)
        (helpers / "send-controller.sh").write_text("exit 0\n")
        (helpers / "ps5-console.py").write_text(
            "import os, sys\nfrom pathlib import Path\n"
            "op = sys.argv[1]\nmarker = Path(os.environ['MARKER'])\n"
            "if op == 'install': marker.touch()\n"
            "if op == 'size': print(54 if os.environ['LEGACY'] == '1' and "
            "sys.argv[2].endswith('/download0/app.log') else 0); sys.exit(0)\n"
            "if op == 'fetch': print('evidence', *sys.argv[3:])\n"
            "if op == 'titles' and os.environ['TITLES_ERROR'] == '1': sys.exit(4)\n"
            "print({'titles':'running: none', 'state':os.environ['AFTER'] if marker.exists() "
            "else 'closed', 'errors':'error records: 0', 'where':'folder /data/homebrew/' "
            "+ sys.argv[-1]}.get(op,''))\n")
        marker = self.root / 'installed'
        env = dict(os.environ, PS5_HOST="fixture", PS5_LOCK=str(self.root / 'lock'),
                   PS5_RESULTS=str(self.root / 'logs'), PS5_RUN="0", PS5_SETTLE="0", PS5_KLOG="0",
                   PS5_LAUNCH="1", PS5_CLOSE="0", PS5_READY_LOG="", PS5_OTHER_TITLES="0",
                   MARKER=str(marker), TITLES_ERROR=str(int(titles_error)), AFTER=after,
                   LEGACY=str(int(legacy)), PS5_FALLBACK_LOG=f'/mnt/sandbox/{TITLE}_000/download0/app.log')
        env.pop('PS5_APP_LOG', None)
        if app_log is not None:
            env['PS5_APP_LOG'] = app_log
        return subprocess.run(["bash", helpers / "ps5-cycle.sh", TITLE, self.candidate, *logs],
                              env=env, text=True, capture_output=True), marker

    def test_normal_simulated_cycle(self):
        proc, marker = self.simulated_cycle()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertTrue(marker.exists())
        self.assertIn(f'evidence /data/{TITLE}/app.log\n', proc.stdout)

    def test_custom_app_log_collected_once_with_other_evidence(self):
        proc, _ = self.simulated_cycle(app_log='/data/custom.log', logs=('/data/other.log', '/data/custom.log'))
        self.assertIn('evidence /data/other.log /data/custom.log\n', proc.stdout)

    def test_disable_default_fetch_preserves_explicit_logs(self):
        proc, _ = self.simulated_cycle(app_log='', logs=('/data/other.log',))
        self.assertIn('evidence /data/other.log\n', proc.stdout)

    def test_legacy_evidence_is_fetched_once_while_running(self):
        legacy = f'/mnt/sandbox/{TITLE}_000/download0/app.log'
        proc, _ = self.simulated_cycle(legacy=True, logs=(legacy, '/data/other.log'))
        evidence = [line for line in proc.stdout.splitlines() if line.startswith('evidence ')]
        self.assertEqual(evidence, [f'evidence {legacy}', 'evidence /data/other.log'])

    @expectedFailure
    def test_unknown_foreground_stops_install(self):
        proc, marker = self.simulated_cycle(titles_error=True)
        self.assertTrue(proc.returncode != 0 and not marker.exists())

    @expectedFailure
    def test_unobserved_launch_is_inconclusive(self):
        proc, _ = self.simulated_cycle(after="closed")
        self.assertNotEqual(proc.returncode, 0)

    @expectedFailure
    def test_extra_manifest_entry_stops_before_connect(self):
        (self.candidate / "extra").touch()
        self.assertIn("differs from its SHA256SUMS", self.cycle().stdout)

    @expectedFailure
    def test_preserve_previous_command_on_interrupted_promotion(self):
        self.ftp.files["/command"] = b"old"
        self.ftp.dropped = True
        with self.assertRaises(OSError):
            self.invoke("put", self.candidate / "asset", "/command")
        self.assertEqual(self.ftp.files.get("/command"), b"old")

    @expectedFailure
    def test_preserve_previous_evidence_on_failed_fetch(self):
        evidence = self.root / "previous"
        evidence.write_bytes(b"record")
        self.invoke("fetch", self.root, "/previous")
        self.assertTrue(evidence.is_file() and evidence.read_bytes() == b"record")

    @expectedFailure
    def test_settle_rejects_same_size_asset_corruption(self):
        for item in self.candidate.rglob("*"):
            if item.is_file():
                self.ftp.files[f"/data/homebrew/{TITLE}/{item.relative_to(self.candidate)}"] = item.read_bytes()
        self.ftp.files[f"/data/homebrew/{TITLE}/asset"] = b"oops"
        with mock.patch.dict(os.environ, PS5_INSTALL_ROOT="/data/homebrew"), self.assertRaises(SystemExit):
            self.invoke("settle", TITLE, self.candidate, "0")


if __name__ == "__main__":
    main(verbosity=2)
