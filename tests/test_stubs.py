# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026 mFat <newmfat@gmail.com> and the gtkghostty contributors
"""The committed type stubs match the API that was just built."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / "stubs" / "gi-stubs" / "repository" / "GtkGhostty.pyi"


def _built_gir() -> Path | None:
    for directory in os.environ.get("GI_TYPELIB_PATH", "").split(os.pathsep):
        for candidate in (Path(directory) / "GtkGhostty-1.gir",
                          Path(directory).parent.parent / "share" / "gir-1.0" / "GtkGhostty-1.gir"):
            if candidate.is_file():
                return candidate
    return None


def test_stubs_are_up_to_date(tmp_path):
    gir = _built_gir()
    if gir is None:
        pytest.skip("no built GtkGhostty-1.gir next to the typelib")
    fresh = tmp_path / "GtkGhostty.pyi"
    subprocess.run([sys.executable, str(ROOT / "tools" / "gen_stubs.py"), str(gir), str(fresh)],
                   check=True, capture_output=True)
    assert fresh.read_text(encoding="utf-8") == COMMITTED.read_text(encoding="utf-8"), (
        "stubs are stale: run python3 tools/gen_stubs.py <build>/src/GtkGhostty-1.gir")
