import json

from retrieval_lab.evals.judge import Judge
from retrieval_lab.llm.base import ABSTAIN_TOKEN, AnswerInputs, LLMRequest, SourcePassage
from retrieval_lab.llm.fake import FakeLLM

SOURCES = [
    SourcePassage(
        marker=1,
        chunk_id="c:1",
        title="Constitution",
        text="The Senate shall have the sole Power to try all Impeachments. It meets in the Capitol.",
    ),
    SourcePassage(
        marker=2, chunk_id="c:2", title="Candle", text="Capillary attraction lifts melted wax up the wick."
    ),
]


async def _answer(question: str) -> str:
    request = LLMRequest(system="", prompt="", inputs=AnswerInputs(question=question, sources=SOURCES))
    return (await FakeLLM().complete(request)).text


async def test_answers_extractively_with_citation() -> None:
    text = await _answer("Who has the power to try impeachments?")
    assert "sole Power to try all Impeachments" in text
    assert "[1]" in text


async def test_abstains_without_overlap() -> None:
    assert await _answer("What is the airspeed of a swallow?") == ABSTAIN_TOKEN


async def test_usage_is_priced_against_reference_model() -> None:
    request = LLMRequest(
        system="sys", prompt="p" * 400, inputs=AnswerInputs(question="wick wax", sources=SOURCES)
    )
    response = await FakeLLM(cost_reference_model="claude-sonnet-5-5").complete(request)
    assert response.usage.input_tokens > 100
    assert response.usage.cost_usd > 0


async def test_judge_flags_unsupported_claims() -> None:
    judge = Judge(FakeLLM())
    contexts = [SOURCES[0].text]
    supported = await judge.faithfulness(
        "Who tries impeachments?", "The Senate tries all Impeachments [1].", contexts
    )
    invented = await judge.faithfulness(
        "Who tries impeachments?",
        "The Supreme Court tries impeachments in public hearings every spring.",
        contexts,
    )
    assert supported.faithful and supported.score == 1.0
    assert not invented.faithful


async def test_relevance_scores_scale_to_unit_interval() -> None:
    judgement = await Judge(FakeLLM()).relevance("Who tries impeachments?", "The Senate tries impeachments.")
    assert 0.0 <= judgement.score <= 1.0
    assert judgement.verdict.score >= 3


async def test_synthesized_question_is_valid_json() -> None:
    from retrieval_lab.llm.base import SynthesisInputs

    request = LLMRequest(
        system="",
        prompt="",
        inputs=SynthesisInputs(title="Flatland: A Romance", heading="Section 1", passage=SOURCES[0].text * 2),
    )
    payload = json.loads((await FakeLLM().complete(request)).text)
    assert payload["question"].endswith("?")
    assert payload["evidence"] in SOURCES[0].text * 2
