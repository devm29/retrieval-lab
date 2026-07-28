from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from pydantic import SecretStr

from retrieval_lab.api.app import create_app
from retrieval_lab.container import Container
from retrieval_lab.settings import Settings

pytestmark = pytest.mark.db


@asynccontextmanager
async def _client(settings: Settings, container: Container) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, container)

    async def boom() -> None:
        raise RuntimeError("kaboom")

    app.add_api_route("/api/boom", boom)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as http:
            yield http


@pytest.fixture(scope="module")
async def client(settings: Settings, container: Container) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(settings, container) as http:
        yield http


async def test_health_reports_offline_stack(client: httpx.AsyncClient) -> None:
    body = (await client.get("/health")).json()
    assert body["status"] == "ok"
    assert body["offline"] is True
    assert body["chunk_count"] > 1000


async def test_query_returns_answer_with_citations(client: httpx.AsyncClient) -> None:
    response = await client.post("/query", json={"question": "Who presides when the President is tried?"})
    assert response.status_code == 200
    body = response.json()
    assert body["config"]["name"] == "hybrid-rerank"
    assert body["config"]["is_latest"] is True
    assert body["result"]["answer"]["citations"]
    assert body["result"]["timings_ms"]["total"] > 0


async def test_unknown_config_is_404_with_error_envelope(client: httpx.AsyncClient) -> None:
    response = await client.post("/query", json={"question": "anything at all", "config": "nope"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_validation_errors_use_the_envelope(client: httpx.AsyncClient) -> None:
    response = await client.post("/query", json={"question": ""})
    assert response.status_code == 422
    assert response.json()["error"]["details"]


async def test_new_spec_creates_a_new_version(client: httpx.AsyncClient) -> None:
    spec = {"kind": "hybrid", "top_k": 8, "rrf_k": 30}
    first = await client.post("/configs", json={"name": "api-hybrid", "spec": spec})
    again = await client.post("/configs", json={"name": "api-hybrid", "spec": spec})
    changed = await client.post("/configs", json={"name": "api-hybrid", "spec": {**spec, "rrf_k": 90}})
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["config"]["version"] == 1
    assert changed.json()["config"]["version"] == 2
    assert again.json()["config"]["is_latest"] is True
    stale = await client.post("/configs", json={"name": "api-hybrid", "spec": spec})
    assert stale.json()["config"]["version"] == 1 and stale.json()["config"]["is_latest"] is False
    assert (await client.get("/configs/api-hybrid")).json()["is_latest"] is True
    assert (await client.get("/configs/api-hybrid@1")).json()["is_latest"] is False


async def test_golden_evidence_is_validated(client: httpx.AsyncClient) -> None:
    bad = await client.post(
        "/golden",
        json={
            "question": "What is the wick made of?",
            "document_slug": "flatland",
            "evidence": "not in the book",
        },
    )
    assert bad.status_code == 422
    good = await client.post(
        "/golden",
        json={
            "question": "What shape are women in Flatland?",
            "document_slug": "flatland",
            "evidence": "Our Women are Straight Lines.",
        },
    )
    assert good.status_code == 201
    question_id = good.json()["id"]
    rejected = await client.patch(f"/golden/{question_id}", json={"status": "rejected"})
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["reviewed_at"] is not None


async def test_marking_a_question_unanswerable_drops_its_evidence(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/golden",
        json={
            "question": "How many sides does a Square have in Flatland?",
            "document_slug": "flatland",
            "evidence": "Our Women are Straight Lines.",
        },
    )
    assert created.status_code == 201
    patched = await client.patch(
        f"/golden/{created.json()['id']}", json={"answerable": False, "question": "  Out of scope now?  "}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["answerable"] is False
    assert body["document_slug"] is None and body["evidence"] is None
    assert body["question"] == "Out of scope now?"
    await client.patch(f"/golden/{body['id']}", json={"status": "rejected"})


async def test_synthesize_fills_the_review_queue(client: httpx.AsyncClient) -> None:
    response = await client.post("/golden/synthesize", json={"count": 3})
    assert response.status_code == 201
    listing = (await client.get("/golden", params={"status": "proposed"})).json()
    assert listing["counts"]["proposed"] >= response.json()["created"]


async def test_run_lifecycle_detail_baseline_and_gate(client: httpx.AsyncClient) -> None:
    created = await client.post("/runs", json={"config": "hybrid-rrf", "label": "api test"})
    assert created.status_code == 202
    run_id = created.json()["id"]
    for _ in range(200):
        run = (await client.get(f"/runs/{run_id}")).json()
        if run["status"] in {"completed", "failed"}:
            break
        await asyncio.sleep(0.1)
    assert run["status"] == "completed", run.get("error")
    assert run["summary"]["metrics"]["ndcg_at_k"] is not None

    results = (await client.get(f"/runs/{run_id}/results", params={"page_size": 5})).json()
    assert results["total"] == run["question_count"]
    question_id = results["items"][-1]["question_id"]
    detail = (await client.get(f"/runs/{run_id}/results/{question_id}")).json()
    assert detail["retrieved"] and detail["result"]["question"]

    assert (await client.get(f"/runs/{run_id}/gate")).status_code == 422
    assert (await client.post("/baselines", json={"run_id": run_id})).status_code == 201
    gate = (await client.get(f"/runs/{run_id}/gate")).json()
    assert gate["passed"] is True

    board = (await client.get("/leaderboard")).json()
    assert any(row["config"]["name"] == "hybrid-rrf" for row in board)
    history = (await client.get("/configs/hybrid-rrf/history")).json()
    assert history


async def test_judge_calibration_round_trip(client: httpx.AsyncClient) -> None:
    created = (await client.post("/judge/calibration")).json()
    assert -1.0 <= created["report"]["kappa"] <= 1.0
    latest = (await client.get("/judge/calibration")).json()
    assert latest["id"] == created["id"]


async def test_null_for_a_required_golden_field_is_422(client: httpx.AsyncClient) -> None:
    listing = (await client.get("/golden", params={"status": "accepted", "page_size": 1})).json()
    question_id = listing["items"][0]["id"]
    for field in ("question", "answerable", "status"):
        response = await client.patch(f"/golden/{question_id}", json={field: None})
        assert response.status_code == 422, field
        assert response.json()["error"]["code"] == "validation_failed"


async def test_malformed_config_version_is_422(client: httpx.AsyncClient) -> None:
    assert (await client.get("/configs/bm25@abc")).status_code == 422
    response = await client.post("/query", json={"question": "anything at all", "config": "bm25@1x"})
    assert response.status_code == 422


async def test_concurrent_registrations_get_distinct_versions(client: httpx.AsyncClient) -> None:
    specs = [{"kind": "bm25", "top_k": k} for k in (3, 4, 5, 6)]
    responses = await asyncio.gather(
        *(client.post("/configs", json={"name": "race", "spec": spec}) for spec in specs)
    )
    assert [r.status_code for r in responses] == [201] * 4
    assert sorted(r.json()["config"]["version"] for r in responses) == [1, 2, 3, 4]


async def test_run_k_beyond_limit_is_rejected(client: httpx.AsyncClient) -> None:
    assert (await client.post("/runs", json={"config": "bm25", "k": 51})).status_code == 422


async def test_unhandled_errors_keep_the_envelope_and_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/boom", headers={"x-request-id": "trace-123"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert response.headers["x-request-id"] == "trace-123"
    forged = await client.get("/health", headers={"x-request-id": "x" * 200})
    assert forged.headers["x-request-id"] != "x" * 200


async def test_token_guards_mutating_routes(settings: Settings, container: Container) -> None:
    secured = settings.model_copy(update={"api_token": SecretStr("s3cret")})
    async with _client(secured, container) as http:
        assert (await http.get("/configs")).status_code == 200
        denied = await http.post("/query", json={"question": "Who presides at impeachment?"})
        assert denied.status_code == 401
        allowed = await http.post(
            "/query",
            json={"question": "Who presides at impeachment?"},
            headers={"authorization": "Bearer s3cret"},
        )
        assert allowed.status_code == 200


async def test_concurrent_runs_are_capped(settings: Settings, container: Container) -> None:
    capped = settings.model_copy(update={"max_active_runs": 1})
    async with _client(capped, container) as http:
        first = await http.post("/runs", json={"config": "bm25", "mode": "retrieval"})
        second = await http.post("/runs", json={"config": "bm25", "mode": "retrieval"})
        assert first.status_code == 202
        assert second.status_code == 429
        run_id = first.json()["id"]
        for _ in range(200):
            if (await http.get(f"/runs/{run_id}")).json()["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.05)


async def test_simultaneous_run_requests_respect_the_cap(settings: Settings, container: Container) -> None:
    capped = settings.model_copy(update={"max_active_runs": 1})
    async with _client(capped, container) as http:
        responses = await asyncio.gather(
            *(http.post("/runs", json={"config": "bm25", "mode": "retrieval"}) for _ in range(3))
        )
        assert sorted(r.status_code for r in responses) == [202, 429, 429]
        run_id = next(r.json()["id"] for r in responses if r.status_code == 202)
        for _ in range(200):
            if (await http.get(f"/runs/{run_id}")).json()["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.05)
