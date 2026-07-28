from __future__ import annotations

import math
import re
import time

from retrieval_lab.llm.base import (
    ABSTAIN_TOKEN,
    AnswerInputs,
    ClaimVerdict,
    ContextInputs,
    ContextVerdict,
    FaithfulnessInputs,
    FaithfulnessVerdict,
    LLMRequest,
    LLMResponse,
    RelevanceInputs,
    RelevanceVerdict,
    RewriteInputs,
    SynthesisInputs,
    SynthesizedQuestion,
)
from retrieval_lab.llm.pricing import price_usage
from retrieval_lab.text import content_terms, estimate_tokens, split_sentences, strip_citations

_SUPPORT_THRESHOLD = 0.6
_GROUNDING_SLIP_BELOW = 0.5
_CONTEXT_USEFUL_AT = 0.5
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "old": ("age",),
    "age": ("years",),
    "long": ("years", "term"),
    "speed": ("velocity",),
    "fast": ("velocity",),
    "quickly": ("velocity",),
    "bright": ("brilliancy", "luminous"),
    "war": ("warfare",),
    "battle": ("fight",),
    "remove": ("removal", "impeachment"),
    "shape": ("figure",),
    "class": ("order",),
    "important": ("prominent", "emphatic"),
    "short": ("concise",),
}


class FakeLLM:
    """Deterministic stand-in for a hosted model.

    Answers extractively from the supplied sources, judges by lexical support,
    and writes questions from templates. It is good enough to make offline evals
    meaningful (better retrieval produces better answers) without network calls.
    """

    def __init__(self, model: str = "fake-extractive-v1", cost_reference_model: str | None = None) -> None:
        self._model = model
        self._cost_reference_model = cost_reference_model

    @property
    def model(self) -> str:
        return self._model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        inputs = request.inputs
        match inputs:
            case AnswerInputs():
                text = self._answer(inputs)
            case RewriteInputs():
                text = self._rewrite(inputs)
            case FaithfulnessInputs():
                text = self._judge_faithfulness(inputs).model_dump_json()
            case RelevanceInputs():
                text = self._judge_relevance(inputs).model_dump_json()
            case ContextInputs():
                text = self._judge_context(inputs).model_dump_json()
            case SynthesisInputs():
                text = self._synthesize(inputs).model_dump_json()
        usage = price_usage(
            self._cost_reference_model or self._model,
            estimate_tokens(request.system) + estimate_tokens(request.prompt),
            estimate_tokens(text),
        )
        return LLMResponse(
            text=text,
            model=self._model,
            usage=usage,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _answer(self, inputs: AnswerInputs) -> str:
        query = set(content_terms(inputs.question))
        if not query:
            return ABSTAIN_TOKEN
        scored: list[tuple[float, int, int, str]] = []
        for position, source in enumerate(inputs.sources):
            for index, sentence in enumerate(split_sentences(source.text)):
                terms = content_terms(sentence)
                if len(terms) < 3:
                    continue
                overlap = len(query.intersection(terms))
                if overlap == 0:
                    continue
                rank_prior = 1.0 / (1 + 0.15 * position)
                score = overlap / math.sqrt(len(terms)) * rank_prior
                scored.append((score, -position, -index, f"{sentence} [{source.marker}]"))
        if not scored:
            return ABSTAIN_TOKEN
        scored.sort(reverse=True)
        best = scored[0]
        required = 1 if len(query) <= 2 else 2
        if len(query.intersection(content_terms(best[3]))) < required:
            return ABSTAIN_TOKEN
        picked = [best[3]]
        if len(scored) > 1 and scored[1][0] >= best[0] * 0.6:
            picked.append(scored[1][3])
        covered = query.intersection(*(set(content_terms(p)) for p in picked[:1]))
        if len(covered) / len(query) < _GROUNDING_SLIP_BELOW:
            # Hosted models under weak grounding tend to bridge the gap from memory; the
            # fake does the same so faithfulness responds to retrieval quality offline.
            topic = " ".join(sorted(query - covered)[:3])
            picked.append(f"Beyond the cited passage, this is the usual account of {topic}.")
        return " ".join(picked)

    def _rewrite(self, inputs: RewriteInputs) -> str:
        seen: dict[str, None] = {}
        for term in re.findall(r"[A-Za-z][A-Za-z'-]+|\d+", inputs.question):
            lowered = term.lower()
            if content_terms(lowered):
                seen.setdefault(lowered, None)
            for synonym in _SYNONYMS.get(lowered, ()):
                seen.setdefault(synonym, None)
        return " ".join(seen) or inputs.question

    def _judge_faithfulness(self, inputs: FaithfulnessInputs) -> FaithfulnessVerdict:
        context_sentences = [set(content_terms(s)) for c in inputs.contexts for s in split_sentences(c)]
        context_vocab = set().union(*context_sentences) if context_sentences else set()
        # Terms the question already introduced are not new claims the context has to back.
        given = set(content_terms(inputs.question))
        claims: list[ClaimVerdict] = []
        for claim in split_sentences(strip_citations(inputs.answer)):
            terms = set(content_terms(claim))
            if not terms:
                continue
            novel = terms - given or terms
            best_sentence = max((len(novel & s) / len(novel) for s in context_sentences), default=0.0)
            overall = len(novel & context_vocab) / len(novel)
            supported = best_sentence >= _SUPPORT_THRESHOLD or overall >= 0.8
            claims.append(ClaimVerdict(claim=claim, supported=supported))
        return FaithfulnessVerdict(claims=claims)

    def _judge_relevance(self, inputs: RelevanceInputs) -> RelevanceVerdict:
        question = set(content_terms(inputs.question))
        answer = set(content_terms(strip_citations(inputs.answer)))
        if not question or not answer:
            return RelevanceVerdict(score=1, reason="The answer does not address the question.")
        coverage = len(question & answer) / len(question)
        score = 1 + round(4 * coverage)
        return RelevanceVerdict(score=score, reason=f"Covers {coverage:.0%} of the question's key terms.")

    def _judge_context(self, inputs: ContextInputs) -> ContextVerdict:
        # A passage is useful when it carries most of what the reference adds beyond the question.
        reference = set(content_terms(inputs.reference))
        needed = reference - set(content_terms(inputs.question)) or reference
        if not needed:
            return ContextVerdict(useful=[False] * len(inputs.contexts))
        return ContextVerdict(
            useful=[
                len(needed & set(content_terms(context))) / len(needed) >= _CONTEXT_USEFUL_AT
                for context in inputs.contexts
            ]
        )

    def _synthesize(self, inputs: SynthesisInputs) -> SynthesizedQuestion:
        sentences = [
            s for s in split_sentences(inputs.passage) if 60 <= len(s) <= 320 and not s.startswith("#")
        ]
        if not sentences:
            sentences = split_sentences(inputs.passage) or [inputs.passage]
        evidence = max(sentences, key=_informativeness)
        book = inputs.title.split(":")[0]
        subject = _definition_subject(evidence)
        if subject:
            question = f"In {book}, what is {subject}?"
        else:
            keywords = _keywords(evidence)[:2]
            topic = " and ".join(keywords) if keywords else inputs.heading.lower() or "this passage"
            question = f"What does {book} say about {topic}?"
        return SynthesizedQuestion(question=question, evidence=evidence, answer=evidence)


_PRONOUNS = frozenset({"it", "this", "that", "there", "he", "she", "they", "we", "i", "you", "what", "which"})
_VERBISH = re.compile(r"(?:ly|ed|ing|es)$")


def _keywords(sentence: str) -> list[str]:
    """Rank likely topic nouns: proper nouns first, then long, rarer-looking words."""
    seen: dict[str, float] = {}
    for position, word in enumerate(re.findall(r"[A-Za-z][A-Za-z-]{4,}", sentence)):
        lowered = word.lower()
        if not content_terms(lowered) or _VERBISH.search(lowered) or lowered in seen:
            continue
        proper = word[0].isupper() and position > 0
        seen[lowered if not proper else word] = (2.0 if proper else 0.0) + len(word) / 4
    return [w for w, _ in sorted(seen.items(), key=lambda item: -item[1])]


def _informativeness(sentence: str) -> float:
    terms = content_terms(sentence)
    capitals = len(re.findall(r"(?<!^)\b[A-Z][a-z]+", sentence))
    digits = len(re.findall(r"\d", sentence))
    return len(set(terms)) + 0.5 * capitals + 0.3 * digits


def _definition_subject(sentence: str) -> str | None:
    match = re.match(
        r"^(?:The |A |An )?([A-Za-z][\w\s'-]{2,40}?) (?:is|are|was|were) (?:a|an|the|called)\b", sentence
    )
    if not match:
        return None
    subject = match.group(1).strip()
    words = subject.lower().split()
    if (
        len(words) > 5
        or words[0] in _PRONOUNS
        or _PRONOUNS.intersection(words)
        or {"is", "are", "was"} & set(words)
    ):
        return None
    return f"the {subject.lower()}" if not subject[0].isupper() else subject
