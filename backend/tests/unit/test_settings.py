import pytest
from pydantic import ValidationError

from retrieval_lab.settings import Settings


def test_blank_api_token_leaves_auth_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RLAB_API_TOKEN", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  ")
    settings = Settings(_env_file=None)
    assert settings.api_token is None
    assert settings.anthropic_api_key is None


def test_set_api_token_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RLAB_API_TOKEN", "local-dev-token")
    settings = Settings(_env_file=None)
    assert settings.api_token is not None
    assert settings.api_token.get_secret_value() == "local-dev-token"


def test_blank_key_still_fails_for_the_live_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RLAB_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY is required"):
        Settings(_env_file=None)
