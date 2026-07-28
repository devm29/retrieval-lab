from __future__ import annotations

from collections.abc import Sequence
from html import escape

from retrieval_lab.llm.base import ABSTAIN_TOKEN, AnswerInputs, LLMRequest, SourcePassage
from retrieval_lab.retrieval.types import RetrievedChunk

SYSTEM_PROMPT = f"""You answer questions about a small library of public-domain books.

Use only the numbered sources in the user message. After every sentence that states a fact, cite \
the sources that support it with their numbers in square brackets, for example [2] or [1, 3]. \
Do not cite a source that does not support the sentence. Do not use outside knowledge.

If the sources do not contain enough information to answer, reply with exactly {ABSTAIN_TOKEN} \
and nothing else.

Keep the answer to at most four sentences of plain prose."""


def build_answer_request(question: str, chunks: Sequence[RetrievedChunk], max_tokens: int) -> LLMRequest:
    sources = [
        SourcePassage(
            marker=index,
            chunk_id=chunk.chunk_id,
            title=chunk.document_title,
            text=chunk.content,
        )
        for index, chunk in enumerate(chunks, start=1)
    ]
    rendered = "\n".join(
        f'<source id="{s.marker}" title="{escape(s.title)}" section="{escape(chunk.heading)}">\n'
        f"{escape(s.text, quote=False)}\n</source>"
        for s, chunk in zip(sources, chunks, strict=True)
    )
    prompt = f"<sources>\n{rendered}\n</sources>\n\nQuestion: {question}"
    return LLMRequest(
        system=SYSTEM_PROMPT,
        prompt=prompt,
        inputs=AnswerInputs(question=question, sources=sources),
        max_tokens=max_tokens,
    )
