from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel

from retrieval_lab.retrieval.types import RetrievedChunk

_MARKER_GROUP = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")


class Citation(BaseModel):
    marker: int
    chunk_id: str
    document_title: str
    heading: str
    snippet: str


class ParsedCitations(BaseModel):
    citations: list[Citation]
    invalid_markers: list[int]


def _snippet(text: str, limit: int = 220) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rsplit(" ", 1)[0] + "…"


def parse_citations(answer: str, sources: Sequence[RetrievedChunk]) -> ParsedCitations:
    """Map [n] markers in an answer to the 1-indexed sources they refer to."""
    seen: dict[int, None] = {}
    for group in _MARKER_GROUP.findall(answer):
        for part in re.split(r"[,;]", group):
            seen.setdefault(int(part), None)
    citations: list[Citation] = []
    invalid: list[int] = []
    for marker in seen:
        if 1 <= marker <= len(sources):
            chunk = sources[marker - 1]
            citations.append(
                Citation(
                    marker=marker,
                    chunk_id=chunk.chunk_id,
                    document_title=chunk.document_title,
                    heading=chunk.heading,
                    snippet=_snippet(chunk.content),
                )
            )
        else:
            invalid.append(marker)
    return ParsedCitations(citations=citations, invalid_markers=invalid)
