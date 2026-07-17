"""
docx text extraction for procedure uploads.

Extracts the plain text of an uploaded Word document so the admin can review it
before saving (tables are flattened to text; images/headers/footers are out of
scope — accepted limitation, the admin edits the text before saving).
"""

import io

from app.exceptions import ValidationException

# Hard upload cap. Enforced in the controller before extraction so a huge upload
# is rejected without being fully buffered.
MAX_DOCX_BYTES = 10 * 1024 * 1024  # 10 MB


def extract_text_from_docx(data: bytes) -> str:
    """Extract concatenated paragraph + table text from a .docx byte string.

    Raises ValidationException if the bytes are not a valid Word document (the
    admin uploaded a renamed non-docx file).
    """
    try:
        from docx import Document  # lazy: keeps module import docx-light
    except ImportError as exc:  # pragma: no cover - dep is in requirements
        raise RuntimeError("python-docx is not installed") from exc

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        raise ValidationException("הקובץ אינו מסמך Word תקין (docx)") from exc

    chunks: list[str] = []
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if text:
            chunks.append(text)
    # Flatten tables (rows/cells) so their text isn't silently lost.
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                chunks.append(" | ".join(cells))
    return "\n\n".join(chunks)
