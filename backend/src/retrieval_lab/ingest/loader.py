from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel


class SourceDocument(BaseModel):
    slug: str
    title: str
    author: str | None = None
    source_url: str | None = None
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---\n", 4)
    if end == -1:
        return {}, raw
    meta: dict[str, str] = {}
    for line in raw[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip()
    return meta, raw[end + 5 :].lstrip("\n")


def load_document(path: Path) -> SourceDocument:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    return SourceDocument(
        slug=path.stem,
        title=meta.get("title") or path.stem.replace("-", " ").title(),
        author=meta.get("author"),
        source_url=meta.get("source"),
        content=body,
    )


def load_corpus(directory: Path) -> list[SourceDocument]:
    paths = sorted([*directory.glob("*.md"), *directory.glob("*.txt")])
    if not paths:
        raise FileNotFoundError(f"No .md or .txt documents found in {directory}")
    return [load_document(path) for path in paths]
