from retrieval_lab.generation.citations import parse_citations
from retrieval_lab.retrieval.types import RetrievedChunk


def _chunk(index: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"doc:{index:04d}",
        rank=index,
        document_slug="doc",
        document_title="Doc",
        heading="Section",
        content=f"Content of chunk {index}. " * 30,
        char_start=0,
        char_end=10,
        score=1.0,
        evidence_score=0.9,
    )


SOURCES = [_chunk(i) for i in range(1, 4)]


def test_markers_map_to_sources_in_first_seen_order() -> None:
    parsed = parse_citations("Fact one [2]. Fact two [1, 3]. Again [2].", SOURCES)
    assert [c.marker for c in parsed.citations] == [2, 1, 3]
    assert [c.chunk_id for c in parsed.citations] == ["doc:0002", "doc:0001", "doc:0003"]
    assert parsed.invalid_markers == []


def test_out_of_range_markers_are_reported() -> None:
    parsed = parse_citations("Made up [7] and zero [0].", SOURCES)
    assert parsed.citations == []
    assert parsed.invalid_markers == [7, 0]


def test_snippets_are_truncated_on_word_boundaries() -> None:
    snippet = parse_citations("x [1]", SOURCES).citations[0].snippet
    assert len(snippet) <= 220
    assert snippet.endswith("…")


def test_text_without_markers() -> None:
    assert parse_citations("No citations here.", SOURCES).citations == []
