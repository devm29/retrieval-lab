from __future__ import annotations

from dataclasses import dataclass, field

import anthropic
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from retrieval_lab.db.models import EMBEDDING_DIM
from retrieval_lab.db.session import build_engine, build_session_factory
from retrieval_lab.evals.judge import Judge
from retrieval_lab.evals.runner import EvalRunner
from retrieval_lab.evals.synth import QuestionSynthesizer
from retrieval_lab.generation.service import AnswerService
from retrieval_lab.ingest.chunker import ChunkingParams
from retrieval_lab.ingest.embedder import Embedder, FastEmbedEmbedder, HashingEmbedder
from retrieval_lab.ingest.service import IngestService
from retrieval_lab.llm.anthropic_provider import AnthropicLLM
from retrieval_lab.llm.base import LLMProvider
from retrieval_lab.llm.fake import FakeLLM
from retrieval_lab.retrieval.components import IndexGuard
from retrieval_lab.retrieval.config import AnyPipeline
from retrieval_lab.retrieval.pipeline import RetrievalPipeline
from retrieval_lab.retrieval.rerank import CrossEncoder, FastEmbedCrossEncoder, LexicalCrossEncoder
from retrieval_lab.settings import Settings


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_dim != EMBEDDING_DIM:
        raise ValueError(
            f"The schema stores {EMBEDDING_DIM}-d vectors; RLAB_EMBEDDING_DIM={settings.embedding_dim}"
        )
    if settings.embedder == "hashing":
        return HashingEmbedder(settings.embedding_dim)
    return FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim, settings.model_cache_dir)


def build_cross_encoder(settings: Settings) -> CrossEncoder:
    if settings.reranker == "lexical":
        return LexicalCrossEncoder()
    return FastEmbedCrossEncoder(settings.reranker_model, settings.model_cache_dir)


def build_llms(settings: Settings) -> tuple[LLMProvider, LLMProvider]:
    if settings.llm_provider == "fake" or settings.anthropic_api_key is None:
        reference = settings.cost_reference_model
        return (
            FakeLLM("fake-extractive-v1", cost_reference_model=reference),
            FakeLLM("fake-judge-v1", cost_reference_model=reference),
        )
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value(), max_retries=3)
    return AnthropicLLM(client, settings.generation_model), AnthropicLLM(client, settings.judge_model)


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    embedder: Embedder
    cross_encoder: CrossEncoder
    llm: LLMProvider
    judge_llm: LLMProvider
    index_guard: IndexGuard = field(init=False)
    answers: AnswerService = field(init=False)
    judge: Judge = field(init=False)
    runner: EvalRunner = field(init=False)
    synthesizer: QuestionSynthesizer = field(init=False)
    ingest: IngestService = field(init=False)

    def __post_init__(self) -> None:
        self.index_guard = IndexGuard(self.sessions, self.embedder)
        self.answers = AnswerService(self.llm)
        self.judge = Judge(self.judge_llm)
        self.runner = EvalRunner(
            self.sessions,
            self.pipeline,
            self.answers,
            self.judge,
            self.index_guard,
            llm_model=self.llm.model,
            embedding_model=self.embedder.model_name,
            reranker_model=self.cross_encoder.model_name,
            concurrency=self.settings.eval_concurrency,
        )
        self.synthesizer = QuestionSynthesizer(self.sessions, self.llm)
        self.ingest = IngestService(
            self.sessions,
            self.embedder,
            ChunkingParams(chunk_size=self.settings.chunk_size, chunk_overlap=self.settings.chunk_overlap),
            on_index_changed=self.index_guard.reset,
        )

    def pipeline(self, spec: AnyPipeline) -> RetrievalPipeline:
        return RetrievalPipeline(
            spec,
            sessions=self.sessions,
            embedder=self.embedder,
            cross_encoder=self.cross_encoder,
            llm=self.llm,
        )

    async def aclose(self) -> None:
        await self.engine.dispose()


def build_container(settings: Settings) -> Container:
    engine = build_engine(settings)
    llm, judge_llm = build_llms(settings)
    return Container(
        settings=settings,
        engine=engine,
        sessions=build_session_factory(engine),
        embedder=build_embedder(settings),
        cross_encoder=build_cross_encoder(settings),
        llm=llm,
        judge_llm=judge_llm,
    )
