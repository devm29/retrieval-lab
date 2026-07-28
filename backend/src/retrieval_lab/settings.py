from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]

LLMProviderName = Literal["anthropic", "fake"]
EmbedderName = Literal["fastembed", "hashing"]
RerankerName = Literal["fastembed", "lexical"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"),
        env_prefix="RLAB_",
        extra="ignore",
    )

    log_level: str = "INFO"
    log_json: bool = False

    database_url: PostgresDsn = PostgresDsn("postgresql+asyncpg://postgres@127.0.0.1:5502/retrieval_lab")
    db_pool_size: int = Field(default=10, ge=1)

    # When set, every mutating request (POST/PATCH) needs `Authorization: Bearer <token>`.
    # Those are the routes that spend Claude tokens in live mode.
    api_token: SecretStr | None = None
    max_active_runs: int = Field(default=2, ge=1, le=16)
    cors_origins: list[str] = ["http://localhost:3102", "http://127.0.0.1:3102"]

    data_dir: Path = PROJECT_ROOT / "data"
    model_cache_dir: Path = PROJECT_ROOT / ".local" / "models"

    llm_provider: LLMProviderName = "fake"
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    generation_model: str = "claude-opus-5-5"
    judge_model: str = "claude-sonnet-5-5"
    # Offline runs still report what the same tokens would have cost on this model.
    cost_reference_model: str = "claude-sonnet-5-5"

    embedder: EmbedderName = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    reranker: RerankerName = "fastembed"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    chunk_size: int = Field(default=900, ge=200)
    chunk_overlap: int = Field(default=150, ge=0)

    eval_concurrency: int = Field(default=4, ge=1, le=32)

    @field_validator("api_token", "anthropic_api_key", mode="before")
    @classmethod
    def _blank_secret_is_unset(cls, value: object) -> object:
        # `RLAB_API_TOKEN=` in .env or `${RLAB_API_TOKEN:-}` in Compose means "not set". Read as an
        # empty token it would switch auth on with a password nobody can send.
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _check_overlap(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.llm_provider == "anthropic" and self.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY is required when RLAB_LLM_PROVIDER=anthropic")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def corpus_dir(self) -> Path:
        return self.data_dir / "corpus"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def offline(self) -> bool:
        return self.llm_provider == "fake"


@lru_cache
def get_settings() -> Settings:
    return Settings()
