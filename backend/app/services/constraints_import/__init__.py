"""Constraints-import pipeline: xlsx → clean structure → availability model.

Step 01 exposes a *pure* parser (bytes → ``ParsedImport``) with no DB access.
Later steps add union-merge, preview, persistence and a summary report.
"""

from .parser import (
    Cell,
    CellKind,
    ParsedGuard,
    ParsedImport,
    parse_constraints_xlsx,
)

__all__ = [
    "Cell",
    "CellKind",
    "ParsedGuard",
    "ParsedImport",
    "parse_constraints_xlsx",
]
