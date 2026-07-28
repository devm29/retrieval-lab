from __future__ import annotations

import time
from typing import Any

import anthropic

from retrieval_lab.errors import ProviderError
from retrieval_lab.llm.base import LLMRequest, LLMResponse
from retrieval_lab.llm.pricing import price_usage
from retrieval_lab.log import get_logger

log = get_logger(__name__)

# Models that accept output_config.effort and server-side refusal fallbacks.
_EFFORT_MODELS = ("claude-opus-5", "claude-sonnet-5", "claude-fable-5", "claude-opus-4-8", "claude-opus-4-7")
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Thinking counts against max_tokens on models where it cannot be turned off, so a truncated
# reply is retried once with a larger budget before it is treated as a failure.
_RETRY_BUDGET_FACTOR = 4
_MAX_BUDGET = 16_000


class AnthropicLLM:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str, *, effort: str = "low") -> None:
        self._client = client
        self._model = model
        self._effort = effort

    @property
    def model(self) -> str:
        return self._model

    def _request_kwargs(self, request: LLMRequest, max_tokens: int) -> dict[str, Any]:
        output_config: dict[str, Any] = {}
        if self._model.startswith(_EFFORT_MODELS):
            output_config["effort"] = self._effort
        if request.json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.json_schema}
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if output_config:
            kwargs["output_config"] = output_config
        if self._model in _FALLBACK_MODELS:
            kwargs["betas"] = [_FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        return kwargs

    async def _create(self, request: LLMRequest, max_tokens: int) -> Any:
        try:
            return await self._client.beta.messages.create(**self._request_kwargs(request, max_tokens))
        except anthropic.RateLimitError as exc:
            raise ProviderError("Anthropic rate limit reached; retry later") from exc
        except anthropic.APIStatusError as exc:
            log.warning("anthropic_error", status=exc.status_code, task=request.inputs.task)
            raise ProviderError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Could not reach the Anthropic API") from exc

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        budget = request.max_tokens
        message = await self._create(request, budget)
        input_tokens, output_tokens = message.usage.input_tokens, message.usage.output_tokens
        if message.stop_reason == "max_tokens" and budget < _MAX_BUDGET:
            budget = min(budget * _RETRY_BUDGET_FACTOR, _MAX_BUDGET)
            log.warning("anthropic_truncated_retry", task=request.inputs.task, max_tokens=budget)
            message = await self._create(request, budget)
            input_tokens += message.usage.input_tokens
            output_tokens += message.usage.output_tokens

        if message.stop_reason != "end_turn":
            log.info("anthropic_stop", task=request.inputs.task, stop_reason=message.stop_reason)
        if message.stop_reason == "refusal":
            raise ProviderError(f"{message.model} declined the {request.inputs.task} request")
        if message.stop_reason == "max_tokens":
            raise ProviderError(
                f"{message.model} ran out of output tokens ({budget}) on the {request.inputs.task} request"
            )
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = price_usage(message.model, input_tokens, output_tokens)
        return LLMResponse(
            text=text.strip(),
            model=message.model,
            usage=usage,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
