#!/usr/bin/env python3
"""Shim to the shared sandbox CLI. Run from this skill directory."""

from __future__ import annotations

import runpy
from pathlib import Path

_TARGET = Path(__file__).resolve().parent.parent.parent / "scripts" / "sandbox.py"
runpy.run_path(str(_TARGET), run_name="__main__")
