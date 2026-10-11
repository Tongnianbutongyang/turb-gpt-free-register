# -*- coding: utf-8 -*-
"""Playwright / Cloak 在系统 Temp 下 mkdtemp 会被权限拦截，统一改到项目 run/tmp。"""
from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAYWRIGHT_TMP_DIR = _PROJECT_ROOT / "run" / "tmp"
_APPLIED = False


def ensure_playwright_tempdir() -> Path:
    global _APPLIED
    PLAYWRIGHT_TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(PLAYWRIGHT_TMP_DIR)
    os.environ["TEMP"] = tmp
    os.environ["TMP"] = tmp
    os.environ["TMPDIR"] = tmp
    _APPLIED = True
    return PLAYWRIGHT_TMP_DIR


ensure_playwright_tempdir()
