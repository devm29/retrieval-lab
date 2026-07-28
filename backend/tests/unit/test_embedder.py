import math

from retrieval_lab.ingest.embedder import HashingEmbedder
from retrieval_lab.retrieval.rerank import LexicalCrossEncoder


async def test_hashing_embedder_is_deterministic_and_normalised() -> None:
    embedder = HashingEmbedder(64)
    first = await embedder.embed_query("The velocity of light")
    second = (await embedder.embed_documents(["The velocity of light"]))[0]
    assert first == second
    assert math.isclose(sum(v * v for v in first), 1.0)


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_hashing_embedder_ranks_shared_terms_higher() -> None:
    embedder = HashingEmbedder(384)
    query = await embedder.embed_query("velocity of light")
    near, far = await embedder.embed_documents(["the velocity of light is constant", "candles burn wax"])
    assert _dot(query, near) > _dot(query, far)


async def test_lexical_cross_encoder_scores_in_unit_interval() -> None:
    scores = await LexicalCrossEncoder().score("candle wick", ["the wick of a candle", "relativity of time"])
    assert scores[0] > scores[1]
    assert all(0.0 <= s <= 1.0 for s in scores)
