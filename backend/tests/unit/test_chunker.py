from itertools import pairwise

import pytest

from retrieval_lab.ingest.chunker import ChunkingParams, chunk_markdown

DOC = """# Title

## First section

Alpha sentence one is here. Alpha sentence two follows it. Alpha sentence three ends the paragraph.

Second paragraph of the first section, written to be long enough to matter.

## Second section

Beta content lives in its own section and should never merge with alpha content.
"""


def test_chunks_are_exact_slices() -> None:
    for chunk in chunk_markdown(DOC, ChunkingParams(chunk_size=200, chunk_overlap=40)):
        assert DOC[chunk.char_start : chunk.char_end] == chunk.content


def test_chunks_do_not_cross_sections_and_carry_heading_path() -> None:
    chunks = chunk_markdown(DOC, ChunkingParams(chunk_size=400, chunk_overlap=0))
    assert [c.heading for c in chunks] == ["First section", "Second section"]
    assert "Beta" not in chunks[0].content
    assert chunks[1].content.startswith("## Second section")


def test_windows_overlap_by_whole_sentences() -> None:
    text = "# T\n\n" + " ".join(f"Sentence number {i} has some words in it." for i in range(30))
    chunks = chunk_markdown(text, ChunkingParams(chunk_size=200, chunk_overlap=80))
    assert len(chunks) > 3
    for left, right in pairwise(chunks):
        assert right.char_start < left.char_end, "consecutive chunks should overlap"
        assert right.char_start > left.char_start, "chunking must make progress"


def test_oversized_sentence_is_split_on_whitespace() -> None:
    text = "# T\n\n" + "word " * 400
    chunks = chunk_markdown(text, ChunkingParams(chunk_size=300, chunk_overlap=0))
    assert all(len(c.content) <= 300 for c in chunks)
    assert sum(len(c.content.split()) for c in chunks) == 400


def test_heading_only_sections_are_skipped() -> None:
    text = "# Book\n\n## Part I\n\n### Chapter 1\n\nThe chapter body is long enough to be kept as a chunk."
    chunks = chunk_markdown(text, ChunkingParams())
    assert len(chunks) == 1
    assert chunks[0].heading == "Part I › Chapter 1"


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError):
        ChunkingParams(chunk_size=200, chunk_overlap=200)
