#!/usr/bin/env python3
"""Rebuild the managers' review PDF from COMBINED_FOR_MANAGERS.md.

Thin wrapper around the reusable `md-to-pdf` skill
(`.claude/skills/md-to-pdf/md_to_pdf.py`). The source Markdown uses
``@@PAGEBREAK@@`` on its own line for hard page breaks.

Usage:
    python3 scripts/build_managers_pdf.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "COMBINED_FOR_MANAGERS.md"
PDF_OUT = ROOT / "מערכת_ניהול_משמרות_סקירה_ותכנון.pdf"
SKILL = ROOT / ".claude" / "skills" / "md-to-pdf" / "md_to_pdf.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location("md_to_pdf", SKILL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    md_to_pdf = _load_skill()
    out = md_to_pdf.convert(SRC, PDF_OUT, rtl=True)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
