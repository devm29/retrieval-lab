from types import SimpleNamespace
from typing import Any, cast

import anthropic
import pytest

from retrieval_lab.errors import ProviderError
from retrieval_lab.llm.anthropic_provider import AnthropicLLM
from retrieval_lab.llm.base import LLMRequest, RewriteInputs


class StubMessages:
    def __init__(self, response: SimpleNamespace) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.response


def _client(stop_reason: str = "end_turn") -> tuple[anthropic.AsyncAnthropic, StubMessages]:
    response = SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=" hello ")],
        stop_reason=stop_reason,
        model="claude-sonnet-5-5",
        usage=SimpleNamespace(input_tokens=1000, output_tokens=100),
    )
    messages = StubMessages(response)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return cast(anthropic.AsyncAnthropic, client), messages


REQUEST = LLMRequest(
    system="sys",
    prompt="prompt",
    inputs=RewriteInputs(question="q"),
    max_tokens=256,
    json_schema={"type": "object"},
)


async def test_builds_request_with_effort_schema_and_fallbacks() -> None:
    client, messages = _client()
    response = await AnthropicLLM(client, "claude-sonnet-5-5").complete(REQUEST)
    call = messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert response.text == "hello"
    assert response.usage.cost_usd == pytest.approx((1000 * 2 + 100 * 10) / 1_000_000)


async def test_haiku_gets_no_effort_or_fallbacks() -> None:
    client, messages = _client()
    await AnthropicLLM(client, "claude-haiku-4-5").complete(REQUEST)
    call = messages.calls[0]
    assert "fallbacks" not in call
    assert "effort" not in call["output_config"]


async def test_refusal_raises_provider_error() -> None:
    client, _ = _client(stop_reason="refusal")
    with pytest.raises(ProviderError, match="declined"):
        await AnthropicLLM(client, "claude-opus-5-5").complete(REQUEST)


class SequencedMessages(StubMessages):
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        super().__init__(responses[0])
        self.responses = responses

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.responses[min(len(self.calls), len(self.responses)) - 1]


def _response(stop_reason: str, text: str = "ok") -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


async def test_truncated_reply_is_retried_with_a_larger_budget() -> None:
    messages = SequencedMessages([_response("max_tokens", "par"), _response("end_turn", "full answer")])
    client = cast(anthropic.AsyncAnthropic, SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    response = await AnthropicLLM(client, "claude-opus-5-5").complete(REQUEST)
    assert [c["max_tokens"] for c in messages.calls] == [256, 1024]
    assert response.text == "full answer"
    assert response.usage.input_tokens == 20


async def test_reply_truncated_twice_raises() -> None:
    messages = SequencedMessages([_response("max_tokens")])
    client = cast(anthropic.AsyncAnthropic, SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    with pytest.raises(ProviderError, match="ran out of output tokens"):
        await AnthropicLLM(client, "claude-opus-5-5").complete(REQUEST)
