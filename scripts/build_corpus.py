"""Rebuild data/corpus from Project Gutenberg plain-text editions.

The generated markdown is checked in, so this only needs to run when the
book list changes. Usage: python scripts/build_corpus.py [raw_dir]
"""

from __future__ import annotations

import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "corpus"


@dataclass(frozen=True)
class Book:
    gutenberg_id: int
    slug: str
    title: str
    author: str
    year: int
    start: str
    end: str | None = None
    heading_patterns: tuple[str, ...] = ()
    subheading_patterns: tuple[str, ...] = ()
    caps_headings: bool = False
    wrap_headings: bool = False
    start_occurrence: int = 0
    skip_patterns: tuple[str, ...] = field(default_factory=tuple)


BOOKS = (
    Book(
        30155,
        "relativity",
        "Relativity: The Special and General Theory",
        "Albert Einstein (tr. Robert W. Lawson)",
        1920,
        start=r"^PREFACE$",
        caps_headings=True,
        skip_patterns=(r"^A\. EINSTEIN$", r"^ALBERT EINSTEIN"),
    ),
    Book(
        37134,
        "elements-of-style",
        "The Elements of Style",
        "William Strunk Jr.",
        1920,
        start=r"^I\. INTRODUCTORY$",
        wrap_headings=True,
        end=r"^VII\. EXERCISES",
        heading_patterns=(r"^[IVX]+\. [A-Z][A-Z ,'-]+$",),
        subheading_patterns=(r"^\d{1,2}\. [A-Z].{5,120}$",),
    ),
    Book(
        132,
        "art-of-war",
        "The Art of War",
        "Sun Tzu (tr. Lionel Giles)",
        1910,
        start=r"^Chapter I\. LAYING PLANS$",
        heading_patterns=(r"^Chapter [IVX]+\. .+$",),
    ),
    Book(
        5,
        "us-constitution",
        "The Constitution of the United States",
        "Constitutional Convention",
        1787,
        start=r"^We the people",
        heading_patterns=(r"^(?i:article) \d+$",),
    ),
    Book(
        14474,
        "chemical-history-of-a-candle",
        "The Chemical History of a Candle",
        "Michael Faraday",
        1861,
        start=r"^LECTURE I\.$",
        start_occurrence=1,
        heading_patterns=(r"^LECTURE [IVX]+\.$", r"^LECTURE ON PLATINUM\.$"),
        end=r"^INDEX\.?$",
    ),
    Book(
        201,
        "flatland",
        "Flatland: A Romance of Many Dimensions",
        "Edwin A. Abbott",
        1884,
        start=r"^PART I:  THIS WORLD$",
        start_occurrence=1,
        wrap_headings=True,
        heading_patterns=(r"^PART [IV]+:.+$",),
        subheading_patterns=(r"^Section \d+\.\s+.+$",),
    ),
)

CAPS_LINE = re.compile(r"^[A-Z0-9][A-Z0-9 ,.;:'’\-()“”\"?]{3,100}$")
ROMAN_ONLY = re.compile(r"^[IVXL]+\.$")
ROMAN_WORD = re.compile(r"^[IVXL]+[.:]?$")
SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}


def smart_title(text: str) -> str:
    words = text.split()
    out: list[str] = []
    for index, word in enumerate(words):
        letters = [c for c in word if c.isalpha()]
        shouting = len(letters) > 1 and all(c.isupper() for c in letters)
        after_break = index == 0 or out[-1].endswith((".", ":")) or bool(ROMAN_WORD.match(out[-1]))
        if not shouting or ROMAN_WORD.match(word):
            out.append(word)
        elif not after_break and word.lower() in SMALL_WORDS:
            out.append(word.lower())
        else:
            out.append("-".join(part[:1].upper() + part[1:].lower() for part in word.split("-")))
    return " ".join(out)


def fetch(book: Book, raw_dir: Path) -> str:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"pg{book.gutenberg_id}.txt"
    if not path.exists():
        url = f"https://www.gutenberg.org/cache/epub/{book.gutenberg_id}/pg{book.gutenberg_id}.txt"
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())
    return path.read_text(encoding="utf-8-sig")


def body_lines(book: Book, text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    start_marker = next(i for i, line in enumerate(lines) if line.startswith("*** START OF"))
    end_marker = next(i for i, line in enumerate(lines) if line.startswith("*** END OF"))
    lines = lines[start_marker + 1 : end_marker]
    starts = [i for i, line in enumerate(lines) if re.match(book.start, line.strip())]
    start = starts[book.start_occurrence]
    lines = lines[start:]
    if book.end:
        end = next((i for i, line in enumerate(lines) if re.match(book.end, line)), len(lines))
        lines = lines[:end]
    return lines


def classify(book: Book, line: str, prev_blank: bool) -> str | None:
    stripped = line.strip()
    if not stripped or not prev_blank:
        return None
    if any(re.match(p, stripped) for p in book.heading_patterns):
        return "##"
    if any(re.match(p, stripped) for p in book.subheading_patterns):
        return "###"
    if book.caps_headings and (CAPS_LINE.match(stripped) or ROMAN_ONLY.match(stripped)):
        letters = [c for c in stripped if c.isalpha()]
        if letters and all(c.isupper() for c in letters):
            return "##"
    return None


def to_markdown(book: Book, lines: list[str]) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    pending_heading: list[str] = []
    heading_level = "##"
    prev_blank = True

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(" ".join(part.strip() for part in paragraph))
            paragraph.clear()

    def flush_heading() -> None:
        if pending_heading:
            title = " ".join(" ".join(pending_heading).split())
            if ROMAN_ONLY.match(title):
                return
            title = smart_title(title)
            blocks.append(f"{heading_level} {title}")
            pending_heading.clear()

    for line in lines:
        stripped = line.strip()
        if any(re.match(p, stripped) for p in book.skip_patterns):
            continue
        level = classify(book, line, prev_blank or bool(pending_heading))
        if level and not paragraph:
            if pending_heading and level != heading_level:
                flush_heading()
            heading_level = level
            pending_heading.append(stripped.rstrip(":"))
            prev_blank = False
            continue
        if pending_heading and stripped and book.wrap_headings and len(pending_heading) < 3:
            pending_heading.append(stripped)
            continue
        if not stripped:
            flush_heading()
            flush_paragraph()
            prev_blank = True
            continue
        flush_heading()
        if line.startswith("    ") and not paragraph:
            blocks.append(stripped)
        else:
            paragraph.append(stripped)
        prev_blank = False

    flush_heading()
    flush_paragraph()
    merged = "\n\n".join(b for b in blocks if b.strip())
    return re.sub(r"_([^_]+)_", r"*\1*", merged)


def front_matter(book: Book) -> str:
    return (
        "---\n"
        f"title: {book.title}\n"
        f"author: {book.author}\n"
        f"year: {book.year}\n"
        f"source: https://www.gutenberg.org/ebooks/{book.gutenberg_id}\n"
        "license: Public domain in the USA\n"
        "---\n\n"
    )


def main() -> None:
    raw_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".local" / "raw"
    OUT.mkdir(parents=True, exist_ok=True)
    for book in BOOKS:
        markdown = to_markdown(book, body_lines(book, fetch(book, raw_dir)))
        target = OUT / f"{book.slug}.md"
        target.write_text(front_matter(book) + f"# {book.title}\n\n" + markdown + "\n", encoding="utf-8")
        print(f"{target.relative_to(ROOT)}  {len(markdown):>8,} chars")


if __name__ == "__main__":
    main()
