#!/usr/bin/env python3
"""Convert a Markdown file to a styled PDF (RTL Hebrew by default).

Pipeline: Markdown -> styled HTML -> PDF via LibreOffice headless.

Why this pipeline: it needs no extra Python PDF deps (only the system
``python3-markdown``) and produces clean RTL Hebrew output with proper fonts
("Noto Sans Hebrew"), colored headers, boxed blockquotes, and styled tables.

Hard page breaks: put ``@@PAGEBREAK@@`` on its own line in the Markdown.

Usage:
    python3 md_to_pdf.py INPUT.md [-o OUTPUT.pdf] [--ltr] [--title "..."]

Requires: python3-markdown and libreoffice/soffice on PATH.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown  # system package: python3-markdown

PAGE_BREAK = "@@PAGEBREAK@@"
MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "attr_list", "nl2br"]

CSS_TEMPLATE = """
@page {{ size: A4; margin: 2.2cm 2cm; }}
* {{ box-sizing: border-box; }}
body {{
  font-family: "Noto Sans Hebrew", "Noto Sans", "DejaVu Sans", sans-serif;
  direction: {direction};
  text-align: {align};
  color: #2b2b2b;
  font-size: 12.5pt;
  line-height: 1.7;
}}
h1 {{
  color: #3b3b7a; font-size: 22pt;
  border-bottom: 2px solid #3b3b7a; padding-bottom: 8px; margin-top: 0;
}}
h2 {{
  color: #3b3b7a; font-size: 16pt;
  border-bottom: 1px solid #c9c9e0; padding-bottom: 5px; margin-top: 28px;
}}
h3 {{ color: #4a4a8a; font-size: 13.5pt; margin-top: 18px; }}
p, li {{ line-height: 1.7; }}
strong {{ color: #1f1f4a; }}
em {{ color: #555; }}
table {{ border-collapse: collapse; width: 100%; margin: 14px 0; direction: {direction}; }}
th {{
  background: #3b3b7a; color: #fff; font-weight: bold;
  padding: 8px 10px; text-align: {align}; border: 1px solid #3b3b7a;
}}
td {{ padding: 7px 10px; border: 1px solid #c9c9e0; text-align: {align}; vertical-align: top; }}
tr:nth-child(even) td {{ background: #f3f3fa; }}
blockquote {{
  background: #eef0fb; border-{startside}: 4px solid #3b3b7a;
  margin: 14px 0; padding: 10px 16px; border-radius: 4px;
}}
blockquote p {{ margin: 6px 0; }}
hr {{ border: none; border-top: 2px solid #c9c9e0; margin: 18px 0; }}
ul {{ padding-{startside}: 22px; }}
.pagebreak {{ page-break-before: always; }}
"""


def build_html(src: Path, rtl: bool, title: str | None) -> str:
    direction = "rtl" if rtl else "ltr"
    align = "right" if rtl else "left"
    startside = "right" if rtl else "left"
    css = CSS_TEMPLATE.format(direction=direction, align=align, startside=startside)

    segments = src.read_text(encoding="utf-8").split(PAGE_BREAK)
    parts: list[str] = []
    for i, seg in enumerate(segments):
        if i > 0:
            parts.append('<div class="pagebreak"></div>')
        parts.append(markdown.markdown(seg.strip(), extensions=MD_EXTENSIONS))
    body = "\n".join(parts)

    head_title = f"<title>{title}</title>\n" if title else ""
    return (
        f'<!DOCTYPE html>\n<html lang="{"he" if rtl else "en"}" dir="{direction}">\n'
        f'<head>\n<meta charset="utf-8">\n{head_title}<style>{css}</style>\n</head>\n'
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def convert(src: Path, out: Path, rtl: bool = True, title: str | None = None) -> Path:
    """Render ``src`` Markdown to ``out`` PDF. Returns the output path."""
    if not src.exists():
        raise FileNotFoundError(src)
    if shutil.which("soffice") is None:
        raise RuntimeError("soffice (LibreOffice) not found on PATH")

    html = build_html(src, rtl=rtl, title=title)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "doc.html").write_text(html, encoding="utf-8")
        proc = subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf",
             "--outdir", str(tmpdir), str(tmpdir / "doc.html")],
            capture_output=True, text=True, timeout=180,
        )
        produced = tmpdir / "doc.pdf"
        if proc.returncode != 0 or not produced.exists():
            raise RuntimeError(
                "LibreOffice conversion failed:\n" + proc.stdout + proc.stderr
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(produced.read_bytes())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Markdown -> styled PDF (RTL by default)")
    ap.add_argument("input", type=Path, help="source .md file")
    ap.add_argument("-o", "--output", type=Path, help="output .pdf (default: input with .pdf)")
    ap.add_argument("--ltr", action="store_true", help="left-to-right layout (default RTL)")
    ap.add_argument("--title", help="HTML <title> / document title")
    args = ap.parse_args(argv)

    out = args.output or args.input.with_suffix(".pdf")
    try:
        result = convert(args.input, out, rtl=not args.ltr, title=args.title)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {result} ({result.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
