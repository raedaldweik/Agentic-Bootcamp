"""Text out of a document someone attaches to a question."""
from __future__ import annotations

import io

MAX_CHARS = 20_000
MAX_BYTES = 12 * 1024 * 1024
TEXT_TYPES = ("txt", "md", "csv", "json", "log", "xml", "html", "yaml", "yml", "sql", "py")
IMAGE_TYPES = ("png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff")


class Unreadable(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def extract(name: str, data: bytes) -> dict:
    """{name, text, chars, truncated}. Raises Unreadable with a message for the person."""
    if len(data) > MAX_BYTES:
        raise Unreadable(413, "That file is too large. Attach a document under 12 MB.")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "pdf":
        try:
            from pypdf import PdfReader
            text = "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(data)).pages)
        except Exception as e:
            raise Unreadable(422, f"Could not read the PDF: {e}") from e
        if not text.strip():
            raise Unreadable(422, "This PDF has no extractable text (it looks scanned), so the assistant cannot read it.")
    elif ext == "docx":
        try:
            from docx import Document
            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        except Exception as e:
            raise Unreadable(422, f"Could not read the DOCX: {e}") from e
    elif ext in TEXT_TYPES:
        text = data.decode("utf-8", errors="replace")
    elif ext in IMAGE_TYPES:
        raise Unreadable(415, "Images cannot be read yet. Attach the content as a PDF, Word or text file.")
    else:
        raise Unreadable(415, f"Unsupported file type: .{ext or '?'}. Attach a PDF, Word or text file.")
    return {"name": name, "text": text[:MAX_CHARS], "chars": len(text), "truncated": len(text) > MAX_CHARS}
