# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate the two framebuffer captures without any imaging dependencies."""
from pathlib import Path

HEADER = b"P6\n1920 1080\n255\n"


def check_images(before, after):
    for path, expected in [(before, bytes((0, 255, 255))), (after, bytes((255, 255, 0)))]:
        data = Path(path).read_bytes()
        if not data.startswith(HEADER) or len(data) != len(HEADER) + 1920 * 1080 * 3:
            raise ValueError(f"Incomplete or unexpected PPM: {path}")
        offset = len(HEADER) + (600 * 1920 + 200) * 3
        if data[offset:offset + 3] != expected:
            raise ValueError(f"Unexpected state marker: {path}")
