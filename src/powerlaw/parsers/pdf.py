from pathlib import Path
from typing import cast

import fitz


def parse_pdf(path: Path) -> str:
    with fitz.open(path) as document:
        return "\n".join(cast(str, page.get_text("text")) for page in document)
