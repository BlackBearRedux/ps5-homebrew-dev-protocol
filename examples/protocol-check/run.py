# SPDX-License-Identifier: GPL-3.0-or-later
"""Run from Linux or WSL. Usage: python3 run.py FROZEN_TITLE_FOLDER NEW_RESULTS_DIR"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time
import uuid

from check_images import check_images

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts/ps5-console.py"
TITLE = "PPSA99871"
INSTALL = "/data/homebrew/" + TITLE
LIVE = "/mnt/sandbox/" + TITLE + "_000/download0"


def console(*args):
    return subprocess.check_output([sys.executable, CLI, *map(str, args)], text=True).strip()


def run(candidate, out):
    for key in ("PS5_HOST", "PS5_LOCK"):
        if not os.environ.get(key):
            raise ValueError(f"Set {key}")
    if candidate.name != TITLE or json.loads((candidate / "sce_sys/param.json").read_text())["titleId"] != TITLE:
        raise ValueError("Wrong candidate title")
    subprocess.run(["sha256sum", "-c", "--quiet", "../SHA256SUMS"], cwd=candidate, check=True)
    out.mkdir(parents=True, exist_ok=False)
    # A new registration is staged once. Refuse an occupied identity or another mounted source.
    api = runpy.run_path(str(CLI))
    token = uuid.uuid4().hex
    lock = Path(os.environ["PS5_LOCK"])
    with lock.open("x") as f:
        f.write(token)
    try:
        if console("titles") != "running: none":
            raise RuntimeError("Console is in use")
        with api["connect"]() as ftp:
            staged = api["names"](ftp, "/data/homebrew")
            registered = api["names"](ftp, "/user/app")
            if staged is None or registered is None:
                raise RuntimeError("Cannot check existing titles")
            if any(n in staged for n in (TITLE + ".ffpkg", TITLE + ".ffpfsc")):
                raise RuntimeError("Title image already present")
            if TITLE in staged or TITLE in registered:
                if console("where", TITLE) != "folder " + INSTALL:
                    raise RuntimeError("Unexpected existing title or mount")
                remote = json.loads(api["readback"](ftp, INSTALL + "/sce_sys/param.json"))
                if remote != json.loads((candidate / "sce_sys/param.json").read_text()):
                    raise RuntimeError("Existing metadata differs")
            else:
                print(console("install", TITLE, candidate), flush=True)
        for _ in range(30):
            if console("where", TITLE) == "folder " + INSTALL:
                break
            time.sleep(2)
        else:
            raise RuntimeError("Registration not confirmed")
        baseline = console("errors", "1")
    finally:
        if lock.read_text() == token:
            lock.unlink()

    print("Registered. Starting the managed cycle.", flush=True)
    receipt = LIVE + "/accept-" + token + ".txt"
    env = dict(os.environ, PS5_AGENT=token, PS5_RUN="90", PS5_LAUNCH="1", PS5_CLOSE="1",
               PS5_READY_LOG=receipt, PS5_READY_PATTERN="^ACCEPTED$", PS5_RESULTS=str(out),
               PS5_OTHER_TITLES="0", PS5_LOCK_WAIT="0", PS5_KLOG="1")
    args = ["bash", ROOT / "scripts/ps5-cycle.sh", TITLE, candidate, "/data/shadowmount/debug.log"]
    with (out / "cycle.txt").open("w") as log, subprocess.Popen(
            args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
        error = None
        accepted = False
        for line in proc.stdout:
            log.write(line)
            log.flush()
            print(line, end="", flush=True)
            if line.startswith("== launched ") and error is None:
                try:
                    if not lock.read_text().startswith(token + "|"):
                        raise RuntimeError("Test does not own the cycle lock")
                    console("wait", LIVE + "/protocol-log.txt", "^PROTOCOL READY$", "25")
                    if console("state", TITLE) != "running":
                        raise RuntimeError("Test title is not running")
                    cmd = out / "command.txt"
                    cmd.write_bytes(b"NEXT\n")
                    console("put", cmd, LIVE + "/protocol-command.txt")
                    console("wait", LIVE + "/protocol-log.txt", "^PROTOCOL INPUT SAVED$", "25")
                    paths = [LIVE + "/" + n for n in ("before.ppm", "after.ppm", "protocol-log.txt")]
                    console("fetch", out, *paths)
                    before, after, applog = [out / n.strip("/").replace("/", "_") for n in paths]
                    check_images(before, after)
                    if applog.read_text().splitlines() != ["PROTOCOL START V1", "PROTOCOL READY", "PROTOCOL INPUT SAVED"]:
                        raise ValueError("Unexpected app log")
                    cmd = out / "accepted.txt"
                    cmd.write_bytes(b"ACCEPTED\n")
                    console("put", cmd, receipt)
                    accepted = True
                except Exception as exc:
                    error = exc  # Let the bounded cycle collect logs and close the title.
        status = proc.wait()
    if error:
        raise error
    if status or not accepted or console("state", TITLE) != "closed" or console("errors", "1") != baseline:
        raise RuntimeError("Cycle, evidence, or teardown check failed")
    if "PROTOCOL INPUT SAVED" not in (out / "klog.txt").read_text(errors="replace"):
        raise ValueError("Missing kernel log checkpoint")
    digest = hashlib.sha256((candidate / "eboot.bin").read_bytes()).hexdigest()
    print(f"Passed {TITLE}, eboot SHA-256 {digest}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
