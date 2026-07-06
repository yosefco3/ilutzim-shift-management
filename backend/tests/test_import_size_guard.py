"""Tests for xlsx upload caps on POST /admin/import/constraints/preview.

Guards against zip-bomb / oversized-sheet DoS on the single Railway process:
byte cap (413), uncompressed-zip cap (413), and sheet-dimension cap (parser
ValueError → 400 via the controller's existing except handler).
"""

import io

import openpyxl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.controllers.constraints_import_controller import (
    _MAX_UPLOAD_BYTES,
    router,
)
from app.dependencies import get_user_service, require_admin_role
from app.services.constraints_import.parser import (
    _MAX_ROWS,
    parse_constraints_xlsx,
)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    user_svc = AsyncMock()
    user_svc.get_all_users.return_value = []
    app.dependency_overrides[get_user_service] = lambda: user_svc
    app.dependency_overrides[require_admin_role] = lambda: None
    return app


def _upload(client, data, filename="big.xlsx"):
    return client.post(
        "/admin/import/constraints/preview",
        files={"file": (filename, data, _XLSX_MIME)},
    )


def test_oversized_upload_is_413():
    client = TestClient(_make_app())
    resp = _upload(client, b"x" * (_MAX_UPLOAD_BYTES + 1))
    assert resp.status_code == 413, resp.text


def test_non_zip_within_size_is_400():
    client = TestClient(_make_app())
    resp = _upload(client, b"not a zip")
    assert resp.status_code == 400, resp.text


def _huge_sheet_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    # A single far-down cell inflates max_row cheaply, tripping the dimension cap.
    ws.cell(row=_MAX_ROWS + 10, column=1, value="x")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_huge_sheet_raises_value_error():
    with pytest.raises(ValueError, match="too large"):
        parse_constraints_xlsx(_huge_sheet_bytes())


def test_huge_sheet_endpoint_is_400():
    client = TestClient(_make_app())
    resp = _upload(client, _huge_sheet_bytes())
    assert resp.status_code == 400, resp.text
