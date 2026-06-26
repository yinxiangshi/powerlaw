import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from powerlaw.parsers.docx import parse_docx
from powerlaw.parsers.html import parse_html
from powerlaw.parsers.pdf import parse_pdf
from powerlaw.parsers.text import parse_text


@dataclass(frozen=True)
class NormalizedDocument:
    text: str
    content_hash: str
    mime: str


def normalize_file(path: Path) -> NormalizedDocument:
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    mime = mimetypes.guess_type(path.name)[0] or "text/plain"

    if suffix in {".htm", ".html"}:
        text = parse_html(path)
    elif suffix == ".pdf":
        text = parse_pdf(path)
    elif suffix == ".docx":
        text = parse_docx(path)
    else:
        text = parse_text(path)

    return NormalizedDocument(
        text=text,
        content_hash=hashlib.sha256(raw).hexdigest(),
        mime=mime,
    )
