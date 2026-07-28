from __future__ import annotations


class RetrievalLabError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(RetrievalLabError):
    status_code = 404
    code = "not_found"


class ConflictError(RetrievalLabError):
    status_code = 409
    code = "conflict"


class ValidationFailedError(RetrievalLabError):
    status_code = 422
    code = "validation_failed"


class IndexMismatchError(RetrievalLabError):
    """The query-time embedder differs from the one used to build the index."""

    status_code = 409
    code = "index_mismatch"


class ProviderError(RetrievalLabError):
    status_code = 502
    code = "provider_error"


class UnauthorizedError(RetrievalLabError):
    status_code = 401
    code = "unauthorized"


class TooManyRunsError(RetrievalLabError):
    status_code = 429
    code = "too_many_runs"
