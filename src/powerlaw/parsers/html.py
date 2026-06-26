from pathlib import Path

from bs4 import BeautifulSoup


def parse_html(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "lxml")
    return soup.get_text("\n")
