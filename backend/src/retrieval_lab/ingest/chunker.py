from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator

from retrieval_lab.text import estimate_tokens

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_MIN_BODY_CHARS = 40
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])[\"'”’)\]]*\s+|\n\s*\n")


class ChunkingParams(BaseModel):
    chunk_size: int = Field(default=900, ge=200)
    chunk_overlap: int = Field(default=150, ge=0)

    @model_validator(mode="after")
    def _overlap_fits(self) -> ChunkingParams:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class ChunkDraft(BaseModel):
    ordinal: int
    heading: str
    content: str
    char_start: int
    char_end: int
    token_count: int


@dataclass(frozen=True, slots=True)
class _Span:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _Section:
    heading: str
    start: int
    end: int


def _sections(text: str) -> Iterator[_Section]:
    trail: dict[int, str] = {}
    cursor = 0
    heading = ""
    for match in _HEADING.finditer(text):
        yield _Section(heading, cursor, match.start())
        level = len(match.group(1))
        trail = {lvl: title for lvl, title in trail.items() if lvl < level}
        trail[level] = match.group(2).strip()
        # The level-1 heading is the document title, which is stored separately.
        heading = " › ".join(title for lvl, title in sorted(trail.items()) if lvl > 1)
        # Sections start at their heading line so headings stay searchable and quotable.
        cursor = match.start()
    yield _Section(heading, cursor, len(text))


def _sentence_spans(text: str, start: int, end: int, max_len: int) -> Iterator[_Span]:
    cursor = start
    for match in _SENTENCE_BREAK.finditer(text, start, end):
        yield from _bounded(text, cursor, match.start(), max_len)
        cursor = match.end()
    yield from _bounded(text, cursor, end, max_len)


def _bounded(text: str, start: int, end: int, max_len: int) -> Iterator[_Span]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    while end - start > max_len:
        cut = text.rfind(" ", start, start + max_len)
        cut = cut if cut > start else start + max_len
        yield _Span(start, cut)
        start = cut
        while start < end and text[start].isspace():
            start += 1
    if end > start:
        yield _Span(start, end)


def chunk_markdown(text: str, params: ChunkingParams) -> list[ChunkDraft]:
    """Split markdown into heading-scoped, sentence-aligned windows.

    Each chunk is an exact slice of `text`, so `char_start`/`char_end` can be used
    to map golden-set evidence spans onto chunks no matter how they were cut.
    """
    drafts: list[ChunkDraft] = []
    for section in _sections(text):
        spans = list(_sentence_spans(text, section.start, section.end, params.chunk_size))
        index = 0
        while index < len(spans):
            first = index
            while index < len(spans) and spans[index].end - spans[first].start <= params.chunk_size:
                index += 1
            index = max(index, first + 1)
            start, end = spans[first].start, spans[index - 1].end
            content = text[start:end]
            body = "\n".join(line for line in content.splitlines() if not line.startswith("#"))
            if len(body.strip()) >= _MIN_BODY_CHARS:
                drafts.append(
                    ChunkDraft(
                        ordinal=len(drafts),
                        heading=section.heading,
                        content=content,
                        char_start=start,
                        char_end=end,
                        token_count=estimate_tokens(content),
                    )
                )
            if index >= len(spans):
                break
            back = index
            while back - 1 > first and spans[index - 1].end - spans[back - 1].start <= params.chunk_overlap:
                back -= 1
            index = back
    if not drafts and text.strip():
        stripped_start = len(text) - len(text.lstrip())
        drafts.append(
            ChunkDraft(
                ordinal=0,
                heading="",
                content=text.strip(),
                char_start=stripped_start,
                char_end=stripped_start + len(text.strip()),
                token_count=estimate_tokens(text),
            )
        )
    return drafts
