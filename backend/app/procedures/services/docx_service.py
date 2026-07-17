"""
docx text extraction for procedure uploads.

Extracts the plain text of an uploaded Word document so the admin can review it
before saving (tables are flattened to text; images/headers/footers are out of
scope — accepted limitation, the admin edits the text before saving). Bold runs
(plus Heading-style paragraphs and highlighted runs) are preserved as lightweight
``*…*`` markers so the Telegram broadcast can render them bold (see
``app.bot.notifications.send_procedure``); markers never span a paragraph.
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
        text = _paragraph_to_marked_text(paragraph).strip()
        if text:
            chunks.append(text)
    # Flatten tables (rows/cells) so their text isn't silently lost. Tables do
    # not carry bold markers (cell.text drops run formatting) — accepted, same
    # as images/headers/footers being out of scope.
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                chunks.append(" | ".join(cells))
    return "\n\n".join(chunks)


def _paragraph_to_marked_text(paragraph) -> str:
    """Render one paragraph's runs as text, wrapping bold spans in ``*markers*``.

    A run counts as bold when its ``bold`` flag is set, it carries a highlight
    color, or the paragraph itself is a Heading style. Adjacent bold runs merge
    into a single ``*…*`` span (never ``*a**b*``); whitespace-only bold runs get
    no markers; markers never span paragraphs (each paragraph is independent,
    so the Telegram conversion can stay balanced per line).
    """
    try:
        style_name = paragraph.style.name or ""
    except Exception:  # pragma: no cover - defensive: malformed style refs
        style_name = ""
    is_heading = style_name.startswith("Heading")

    # Coalesce adjacent runs that share the same bold flag into one segment so
    # a bold word split across several runs becomes a single *…* span.
    segments: list[tuple[bool, str]] = []  # (is_bold, text)
    for run in paragraph.runs:
        text = run.text or ""
        if text == "":
            continue
        is_bold = (
            bool(run.bold)
            or getattr(run.font, "highlight_color", None) is not None
            or is_heading
        )
        if segments and segments[-1][0] == is_bold:
            prev_bold, prev_text = segments[-1]
            segments[-1] = (prev_bold, prev_text + text)
        else:
            segments.append((is_bold, text))

    out: list[str] = []
    for is_bold, text in segments:
        if is_bold and text.strip():
            out.append(f"*{text}*")
        else:
            out.append(text)
    return "".join(out)
