<div align="center">

<img src="web/src/app/icon.svg" width="64" height="64" alt="Retrieval Lab logo" />

# Retrieval Lab

**Hybrid RAG where retrieval quality is the product, and every change is measured before it ships.**

BM25 + pgvector, fused with RRF, reranked by a cross-encoder, answered with citations,<br/>
scored against a golden set, and guarded by a quality gate that fails when quality drops.

<br/>

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](backend/pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.142-009688?logo=fastapi&logoColor=white)](backend/src/retrieval_lab/api)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](backend/src/retrieval_lab/retrieval/config.py)
[![PostgreSQL + pgvector](https://img.shields.io/badge/PostgreSQL-16%2B%20%C2%B7%20pgvector-4169E1?logo=postgresql&logoColor=white)](backend/migrations)
[![mypy strict](https://img.shields.io/badge/mypy-strict-2A6DB2)](backend/pyproject.toml)
<br/>
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](web)
[![TypeScript strict](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)](web/tsconfig.json)
[![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-Radix-000000?logo=shadcnui&logoColor=white)](web/components.json)
[![License: MIT](https://img.shields.io/badge/License-MIT-34C759)](LICENSE)

[Why](#why-this-exists) · [Features](#features) · [Screenshots](#screenshots) · [Architecture](#architecture) · [Quickstart](#quickstart) · [Metrics](#what-the-numbers-mean) · [API](#api-overview) · [Examples](#request-and-response-examples)

<br/>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/hero-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="docs/screenshots/hero-light.png" />
  <img alt="Retrieval Lab overview: KPI tiles and a leaderboard of five retrieval configs ranked by nDCG@k" src="docs/screenshots/hero-light.png" width="100%" />
</picture>

</div>

---

## Why this exists

Most RAG demos stop at "it answered my question". The questions that matter in production come after that. Did the new chunk size help? Is the reranker worth 500 ms? Did the prompt change make answers less grounded? Without numbers, those are opinions.

Retrieval Lab treats a retrieval pipeline like any other piece of software that can regress:

- **Pipelines are data.** Each retrieval strategy is a versioned, hash-addressed Pydantic config, not a code branch.
- **Quality is measured.** Every config is scored against the same golden set with IR metrics (recall@k, MRR, nDCG@k) and generation metrics (faithfulness, answer relevance, citation accuracy), plus latency and cost for each stage.
- **The judge is checked too.** The LLM-as-judge is calibrated against human labels, and the agreement is reported as Cohen's kappa.
- **Regressions fail the gate.** `rlab eval gate` re-scores a config fully offline and exits non-zero when nDCG or faithfulness drops beyond tolerance, so it can block a merge or a deploy script.

It runs entirely offline by default, using ONNX embeddings, an ONNX cross-encoder and a deterministic fake LLM. Clone it, seed it and gate it without an API key. Switch one env var to use Claude.

### Results on the bundled corpus

These are the stored baselines in [`data/baselines/`](data/baselines): 62 golden questions (56 answerable, 6 out of scope), k = 10, offline mode.

| Config | Pipeline | nDCG@10 | Recall@10 | MRR | Context precision | Faithfulness | p50 latency |
|---|---|---:|---:|---:|---:|---:|---:|
| `hybrid-rerank-rewrite` | rewrite → BM25 ∥ dense → RRF → rerank | **0.897** | 0.964 | **0.874** | **0.840** | **0.956** | 585 ms |
| `hybrid-rerank` | BM25 ∥ dense → RRF → rerank | 0.890 | 0.964 | 0.865 | 0.804 | 0.938 | 553 ms |
| `hybrid-rrf` | BM25 ∥ dense → RRF | 0.853 | 0.964 | 0.817 | 0.785 | 0.935 | 31 ms |
| `bm25` | Postgres FTS with Okapi BM25 | 0.801 | 0.929 | 0.759 | 0.763 | 0.950 | 22 ms |
| `dense` | BGE-small + HNSW | 0.783 | 0.893 | 0.749 | 0.710 | 0.933 | 20 ms |

The trade-off is visible at a glance. Fusion gains about 5 nDCG points over the best single retriever for almost no latency. The cross-encoder adds about 4 more, but it costs more than 15x the latency on CPU.

## Features

<table>
<tr>
<td width="50%" valign="top">

**Hybrid retrieval in Postgres**
- Real Okapi BM25 (k1, b, IDF and document length) computed in SQL over a stored, weighted `tsvector` (heading weighted A, body B), with corpus statistics kept in their own tables.
- Dense search with `pgvector` HNSW (cosine, tunable `ef_search` for each config).
- Weighted Reciprocal Rank Fusion with tunable `rrf_k`. Both retrievers run in parallel with `asyncio.gather`.
- Cross-encoder reranking (MS MARCO MiniLM via fastembed ONNX).
- Optional LLM query rewrite. You choose whether it applies to BM25, dense or both, and whether the reranker scores the original or the rewritten query.

</td>
<td width="50%" valign="top">

**Grounded generation**
- Numbered `<source>` prompt with HTML-escaped passages; inline `[n]` markers are parsed and mapped back to chunk IDs.
- Three abstention paths: no results, top evidence below the config's `abstain_below`, or the model declines.
- Per-stage timings (`rewrite`, `bm25`, `embed`, `dense`, `fusion`, `rerank`, `generate`) and token cost on every response.
- Pluggable LLM provider: Anthropic Claude, or a deterministic offline fake that still reports what the tokens *would* cost.

</td>
</tr>
<tr>
<td valign="top">

**Evaluation harness**
- Span-based IR metrics. Golden questions point at evidence *character spans* rather than chunk IDs, so the same golden set scores any chunking strategy.
- RAGAS-style context precision, claim-level faithfulness, answer relevance, citation accuracy, and abstention accuracy and false-abstention rate.
- p50/p95/mean latency for each stage and token cost for each stage in every run summary.
- Runs are started from the Typer CLI or the API. They are bounded by a semaphore and a `TaskGroup`, so a failure cancels the remaining questions instead of burning tokens.

</td>
<td valign="top">

**Golden set and judge calibration**
- 62 curated seed questions are checked in, including 6 unanswerable ones that test abstention.
- Synthetic question generation from random chunks lands in a review queue. You accept, edit or reject each question, with keyboard shortcuts.
- Evidence quotes are validated to appear verbatim in the source document.
- The judge is calibrated on 26 human-labelled answers. The dashboard shows Cohen's kappa with Landis and Koch bands, a confusion matrix, and every disagreement.

</td>
</tr>
<tr>
<td valign="top">

**Quality gate**
- `rlab eval gate` re-scores a config and diffs the result against the checked-in baseline JSON.
- **Exit 1** when nDCG@k or faithfulness drops beyond tolerance. **Exit 2** when the baseline came from a different environment (another embedder, reranker, LLM, judge, k or golden-set hash), because that diff would be meaningless.
- `--report <file>` appends the verdict as a markdown table, ready to paste into a review.

</td>
<td valign="top">

**Experiment dashboard**
- Leaderboard, side-by-side metric bars, and a quality vs latency scatter plot.
- Run detail with a latency waterfall, token cost, and a per-question table sorted worst first.
- Per-query drill-down that puts the gold evidence next to the retrieved chunks, with the rank of each chunk in every stage (BM25, Dense, RRF and Rerank).
- A playground with clickable citations, a run-diff view, and a pipeline version history.

</td>
</tr>
</table>

## Screenshots

**Playground.** A cited answer where each marker jumps to its source, with a waterfall of where the time went below it.

![Playground answering with inline citations and a per-stage latency waterfall](docs/screenshots/playground.png)

**Drill-down.** Gold evidence next to the retrieved chunks, with the rank from each stage.

![Per-question drill-down showing gold evidence next to the retrieved top 10](docs/screenshots/question-drilldown.png)

**Run detail.** Metrics, p50/p95 for each stage, token cost, and the worst questions first.

![Run detail with retrieval and answer metrics, latency by stage and token cost](docs/screenshots/run-detail.png)

**Compare.** Adding the reranker to RRF: +0.044 nDCG, question by question.

![Compare view of hybrid-rrf against hybrid-rerank with per-question nDCG changes](docs/screenshots/compare.png)

**Gate failure.** BM25 alone against the `hybrid-rerank` baseline: nDCG drops 0.089, beyond the 0.02 tolerance.

![Compare view showing a candidate that would fail the gate on nDCG](docs/screenshots/gate-fail.png)

**Judge calibration.** Cohen's kappa against human labels, and every disagreement.

![Judge calibration with Cohen's kappa, confusion matrix and disagreements](docs/screenshots/judge-calibration.png)

**Abstention.** An out-of-scope question is declined before any model call.

![Playground abstaining on an out-of-scope question](docs/screenshots/playground-abstain.png)

**Golden set.** Synthetic questions wait for review before they count.

![Golden set review queue for synthetic questions](docs/screenshots/golden-review.png)

**Pipelines.** Hash-versioned specs and quality across versions.

![Pipelines page with a versioned spec and quality across versions](docs/screenshots/pipelines.png)

**On a phone.** The sidebar folds away and the tables scroll sideways inside their cards.

<p>
  <img src="docs/screenshots/overview-mobile.png" alt="Overview on a 390 px wide phone screen" width="300" />
  <img src="docs/screenshots/playground-mobile.png" alt="Playground on a 390 px wide phone screen" width="300" />
</p>

All screenshots come from a fresh offline seed (`rlab seed` with the fake LLM). Their numbers can differ from the stored baselines above by a few thousandths, because ONNX scores vary slightly across CPU architectures.

<details>
<summary><b>Full overview page</b></summary>
<br/>
<img src="docs/screenshots/overview.png" alt="Full overview page with leaderboard, metric charts and corpus" />
</details>

## Architecture

### System

```mermaid
flowchart TB
    subgraph Clients
        direction LR
        UI["Next.js dashboard<br/>:3102"]
        CLI["rlab CLI<br/>(Typer)"]
    end

    subgraph API["FastAPI service :8102"]
        Routers["routers<br/>query · runs · golden<br/>configs · judge · system"]
        subgraph Retrieval["retrieval (PipelineConfig)"]
            direction LR
            RW["QueryRewriter<br/>(optional)"] --> BM["Bm25Retriever"]
            RW --> DN["DenseRetriever"]
            BM --> RRF["RrfFusion"]
            DN --> RRF
            RRF --> RR["Reranker"]
        end
        subgraph Generation["generation"]
            direction LR
            AB["abstention check"] --> PR["prompt assembly"] --> CP["citation parser"]
        end
        subgraph Evals["evals"]
            direction LR
            RUN["EvalRunner"] --> MET["metrics (pure)"]
            RUN --> JDG["Judge + kappa"]
            RUN --> BASE["baseline diff"]
        end
        subgraph Ingest["ingest"]
            direction LR
            LD["loader"] --> CH["chunker"] --> EM["embedder"]
        end
    end

    subgraph Models["Local ONNX (fastembed)"]
        direction LR
        BGE["BGE-small<br/>embeddings"]
        CE["MiniLM<br/>cross-encoder"]
    end

    LLM["LLM provider<br/>Claude or offline fake"]
    PG[("PostgreSQL + pgvector<br/>tsvector GIN · HNSW")]
    FILES[["data/<br/>corpus · pipelines<br/>golden · baselines"]]

    UI -- "/api proxy + bearer" --> Routers
    CLI --> RUN
    CLI --> LD
    Routers --> RW
    Routers --> RUN
    RUN --> RW
    RR --> AB
    BM --> PG
    DN --> PG
    DN --> BGE
    RR --> CE
    EM --> BGE
    EM --> PG
    RW -.-> LLM
    PR --> LLM
    JDG --> LLM
    LD --> FILES
    BASE --> FILES
```

### Query flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant W as Next.js proxy
    participant A as FastAPI /api/query
    participant P as RetrievalPipeline
    participant DB as Postgres + pgvector
    participant X as Cross-encoder
    participant L as LLM

    U->>W: question + config
    W->>A: POST /api/query
    A->>DB: resolve config (short session)
    A->>P: retrieve(question)
    opt query_rewrite configured
        P->>L: rewrite to keyword query
    end
    par BM25 branch
        P->>DB: Okapi BM25 over tsvector
    and Dense branch
        P->>P: embed query (BGE ONNX)
        P->>DB: HNSW cosine search (ef_search)
    end
    P->>P: weighted RRF fusion
    P->>X: score top rerank_candidates
    X-->>P: reranked candidates + evidence scores
    alt no results or top evidence below abstain_below
        A-->>U: abstain (no model call, $0)
    else enough evidence
        A->>L: numbered sources + question
        L-->>A: answer with [n] markers
        A->>A: parse citations to chunk ids
        A-->>U: answer, citations, stage timings, cost
    end
```

### Eval and gate flow

```mermaid
sequenceDiagram
    autonumber
    participant S as Caller (shell, hook)
    participant C as rlab eval gate
    participant R as EvalRunner
    participant DB as Postgres
    participant J as Judge
    participant B as data/baselines

    S->>C: rlab eval gate --config hybrid-rerank
    C->>B: read baseline JSON (k, environment, metrics)
    C->>R: run(config, mode=full, k=baseline.k)
    R->>R: index guard (embedder matches index)
    R->>DB: accepted golden questions + evidence spans
    loop each question (bounded concurrency, TaskGroup)
        R->>R: pipeline -> answer
        R->>J: faithfulness, relevance, context usefulness
        R->>DB: store per-question result
    end
    R->>DB: aggregate summary + environment
    R-->>C: RunSummary
    C->>C: compare(): drift check, then metric deltas
    alt environment or k differs
        C-->>S: exit 2 (not comparable)
    else nDCG or faithfulness dropped beyond tolerance
        C-->>S: exit 1 (regressed) + markdown report
    else
        C-->>S: exit 0 (passed)
    end
```

### User flow

```mermaid
flowchart TD
    Start(["Open dashboard"]) --> Overview["Overview<br/>leaderboard + charts"]
    Overview --> Pick{"What next?"}

    Pick -->|"Try a question"| PG["Playground"]
    PG --> Ask["Ask with a chosen config"]
    Ask --> Ans{"Evidence strong enough?"}
    Ans -->|"Yes"| Cited["Answer with clickable citations<br/>+ latency waterfall"]
    Ans -->|"No"| Abstain["Abstains, sources still listed"]

    Pick -->|"Tune retrieval"| Pipes["Pipelines"]
    Pipes --> NewVer["New version from a spec<br/>(hash-versioned)"]
    NewVer --> NewRun["New run"]

    Pick -->|"Grow the golden set"| Golden["Golden set"]
    Golden --> Synth["Generate synthetic questions"]
    Synth --> Review{"Review"}
    Review -->|"Accept or edit"| Accepted["Counts in every run"]
    Review -->|"Reject"| Rejected["Excluded"]

    Pick -->|"Trust the judge?"| Judge["Judge calibration<br/>kappa + disagreements"]

    NewRun --> Detail["Run detail<br/>metrics, gate, cost"]
    Overview --> Detail
    Detail --> Drill["Question drill-down<br/>gold span vs retrieved"]
    Detail --> Cmp["Compare to baseline"]
    Cmp --> Gate{"Passes the gate?"}
    Gate -->|"Yes"| Promote["Promote to baseline"]
    Gate -->|"No"| Pipes
```

### Data model

```mermaid
erDiagram
    DOCUMENTS ||--o{ CHUNKS : "split into"
    PIPELINE_CONFIGS ||--o{ EVAL_RUNS : "evaluated by"
    EVAL_RUNS ||--o{ EVAL_RESULTS : "has"
    GOLDEN_QUESTIONS ||--o{ EVAL_RESULTS : "scored in"
    EVAL_RUNS ||--o| BASELINES : "promoted to"

    DOCUMENTS {
        uuid id PK
        string slug UK
        string title
        text content
        string content_hash
        jsonb chunking
    }
    CHUNKS {
        string id PK
        uuid document_id FK
        int ordinal
        text heading
        text content
        int char_start
        int char_end
        int term_count
        vector embedding "384-d, HNSW cosine"
        tsvector tsv "generated, GIN"
    }
    LEXEME_STATS {
        text lexeme PK
        int ndoc
        float idf
    }
    CORPUS_STATS {
        smallint id PK "always 1"
        int chunk_count
        float avg_term_count
    }
    PIPELINE_CONFIGS {
        uuid id PK
        string name
        int version
        string spec_hash "sha256 of canonical spec"
        string kind
        jsonb spec
    }
    GOLDEN_QUESTIONS {
        uuid id PK
        string external_id UK
        text question
        string document_slug
        text evidence "verbatim span"
        bool answerable
        enum status "proposed, accepted, rejected"
        enum origin "seed, synthetic, manual"
    }
    EVAL_RUNS {
        uuid id PK
        uuid config_id FK
        enum status
        string mode "full or retrieval"
        string trigger "cli, api, ci, seed"
        int k
        jsonb summary "metrics, latency, cost, environment"
    }
    EVAL_RESULTS {
        uuid id PK
        uuid run_id FK
        uuid question_id FK
        float ndcg
        jsonb payload "retrieved, expected, claims, timings"
    }
    BASELINES {
        string config_name PK
        uuid run_id FK
    }
    JUDGE_CALIBRATIONS {
        uuid id PK
        string judge_model
        float kappa
        float agreement
        jsonb payload
    }
```

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | **FastAPI**, Uvicorn, structlog | Async end to end. Typed request and response models, with request-id middleware. |
| Domain models | **Pydantic v2** + pydantic-settings | Pipeline specs are a discriminated union (`kind`), frozen and `extra="forbid"`, then hashed. |
| Storage | **PostgreSQL** + **pgvector**, SQLAlchemy 2 async, asyncpg, Alembic | Lexical and vector search share one store and one transaction. No separate vector DB to keep in sync. |
| Embeddings and reranker | **fastembed** (ONNX): `BAAI/bge-small-en-v1.5`, `Xenova/ms-marco-MiniLM-L-6-v2` | CPU-friendly and deterministic. The runtime is pinned because scores feed the stored baselines. |
| LLM | **Anthropic SDK** (Claude) or an offline `FakeLLM` | The same `LLMProvider` protocol serves generation, rewriting, synthesis and judging. |
| CLI | **Typer** + Rich | `rlab ingest · configs · golden · eval run/gate/compare/baseline · judge calibrate · seed` |
| Web | **Next.js 16** App Router, React 19, **TypeScript strict**, **shadcn/ui** (Radix), Tailwind 4 | A lab-notebook look: IBM Plex Sans and Mono, warm paper neutrals and one ink-teal accent, in light and dark. |
| Data fetching | **TanStack Query** + **zod** | Every API response is validated at runtime against a zod schema. |
| Charts | **Recharts** | Metric bars, a quality vs latency scatter, latency by stage, and quality over time. |
| Quality | pytest (unit + Postgres integration), mypy `--strict`, Ruff, Vitest + RTL, ESLint, Playwright | One `make` line runs all of it. |
| Delivery | Docker Compose | Ports are bound to `127.0.0.1`. The images run as a non-root user. |

## Key engineering decisions

<details open>
<summary><b>Evidence spans, not chunk IDs, as ground truth</b></summary>

A golden set keyed on chunk IDs becomes useless the moment you change the chunker. Each golden question here stores a verbatim evidence quote. At run time, the quote is located in the document and becomes a character span. A chunk's gain is the share of the span it covers that no higher-ranked chunk already covered, so overlapping chunks are not double counted. nDCG uses a greedy ideal ordering over every chunk that overlaps the span. You can change `RLAB_CHUNK_SIZE`, re-ingest, and compare runs from before and after the change.
</details>

<details>
<summary><b>Real BM25 inside Postgres</b></summary>

`ts_rank` is not BM25: it has no IDF and no length normalisation. The BM25 query unnests the stored `tsvector`. It joins each term against a `lexeme_stats` table (IDF from `ts_stat`) and a single-row `corpus_stats` table (avgdl), and it applies Okapi BM25 with `k1` and `b`. The score is also normalised against the best score the query could reach. That makes it usable as an abstention signal, which raw BM25 is not.
</details>

<details>
<summary><b>A calibrated evidence score drives abstention</b></summary>

RRF scores are rank-based and say nothing about absolute relevance, so they cannot drive abstention. Each pipeline exposes the most calibrated signal it has. That is cross-encoder scores after a rerank, cosine similarity for dense and hybrid-RRF, and normalised BM25 for lexical search. `abstain_below` is set for each config, against that config's own signal.
</details>

<details>
<summary><b>The gate only compares like with like</b></summary>

Every run records a `RunEnvironment`: LLM, judge, embedder, reranker and a content hash of the accepted golden set. A baseline produced with a different embedder or golden set is reported as blocking drift and the gate exits 2, rather than passing or failing on a meaningless diff. A changed spec hash is reported but does not block, because catching the effect of a spec change is the gate's job.
</details>

<details>
<summary><b>Hash-versioned configs</b></summary>

A config's identity is the SHA-256 of its canonical JSON spec. Registering an identical spec is a no-op. Any change creates `name@N+1`, and a Postgres advisory lock serialises concurrent registrations. Runs reference an exact version, so history stays honest.
</details>

<details>
<summary><b>Offline by default, honest about it</b></summary>

The fake LLM is deterministic. It extracts sentences for answers, judges claims lexically, and reports what the same tokens would cost on `RLAB_COST_REFERENCE_MODEL`. Offline faithfulness is therefore a *retrieval-coverage proxy*, not a measure of answer quality. This is stated in the dashboard and [below](#what-the-numbers-mean). Set `RLAB_LLM_PROVIDER=anthropic` for real judgements. A truncated Claude reply is retried once with a larger token budget.
</details>

<details>
<summary><b>Failure behaviour</b></summary>

Eval questions run in an `asyncio.TaskGroup` behind a semaphore, so one failure cancels the rest and the run is marked failed with its root cause. On startup, the API marks API runs left over from a crash as interrupted. `RLAB_MAX_ACTIVE_RUNS` returns 429 above the cap. An `IndexGuard` refuses queries when the index was embedded by a different model than the active embedder.
</details>

## Quickstart

Everything runs offline by default. The only downloads are packages and, on the first seed, two small ONNX models (about 150 MB) that are cached afterwards.

### Docker Compose

Needs only Docker.

```bash
docker compose up --build -d                    # postgres (pgvector/pgvector:pg16), api on :8102, web on :3102
docker compose --profile tools run --rm seed    # migrate, index the corpus, load the golden set, run every config
open http://127.0.0.1:3102
docker compose down                             # add -v to drop the database and the model cache
```

`make docker-up` and `make docker-down` wrap the same commands. The seed job takes a few minutes on a laptop CPU, most of it in the cross-encoder runs.

### Local

Python 3.12, Node 22, pnpm 9, and a Postgres with pgvector.

```bash
make install   # backend/.venv (pip, constrained by backend/requirements.lock) + pnpm install
make db        # project-local Postgres 17 + pgvector on :5502, data in .local/ (macOS, Homebrew postgresql@17)
make seed      # migrate, index the corpus, load golden set, run every config, write baselines
make dev       # API on http://127.0.0.1:8102, dashboard on http://127.0.0.1:3102
```

`make db` builds pgvector from its release tarball into `.local/`, without touching the Homebrew install. If you would rather not compile anything, run only the database from Compose (`docker compose up -d postgres`) and point the app at it with `RLAB_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5502/retrieval_lab`.

```bash
backend/.venv/bin/rlab ask "Who presides when the President is tried for impeachment?"
backend/.venv/bin/rlab eval run --config hybrid-rrf --k 20
make gate      # exit 0 pass · 1 regressed · 2 baseline from a different environment
```

### Using Claude instead of the offline model

```bash
export RLAB_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...                # your own key
backend/.venv/bin/rlab judge calibrate      # kappa of the real judge against the human labels
backend/.venv/bin/rlab eval run --config hybrid-rerank
```

Baselines record the models that produced them. A live run compared against an offline baseline exits 2 unless you pass `--allow-drift`.

## Configuration

All settings use the `RLAB_` prefix and can live in `.env` (see [`.env.example`](.env.example)).

| Variable | Default | Purpose |
|---|---|---|
| `RLAB_DATABASE_URL` | `postgresql+asyncpg://postgres@127.0.0.1:5502/retrieval_lab` | Main database |
| `RLAB_TEST_DATABASE_URL` | `…/retrieval_lab_test` | Integration test database |
| `RLAB_LLM_PROVIDER` | `fake` | `fake` (offline, deterministic) or `anthropic` |
| `ANTHROPIC_API_KEY` | — | Required when the provider is `anthropic` |
| `RLAB_GENERATION_MODEL` | `claude-opus-5-5` | Answer generation, rewrite, synthesis |
| `RLAB_JUDGE_MODEL` | `claude-sonnet-5-5` | Faithfulness, relevance, context judge |
| `RLAB_COST_REFERENCE_MODEL` | `claude-sonnet-5-5` | Price list used to cost offline runs |
| `RLAB_EMBEDDER` | `fastembed` | `fastembed` or `hashing` (no download, used by tests) |
| `RLAB_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | 384-d embedding model |
| `RLAB_RERANKER` | `fastembed` | `fastembed` or `lexical` (no download, used by tests) |
| `RLAB_RERANKER_MODEL` | `Xenova/ms-marco-MiniLM-L-6-v2` | Cross-encoder |
| `RLAB_CHUNK_SIZE` / `RLAB_CHUNK_OVERLAP` | `900` / `150` | Chunking, in characters |
| `RLAB_EVAL_CONCURRENCY` | `4` | Questions scored in parallel within a run |
| `RLAB_API_TOKEN` | — | When set, `POST` and `PATCH` require `Authorization: Bearer <token>`. The Next.js proxy adds it on the server, so it never reaches the browser. |
| `RLAB_MAX_ACTIVE_RUNS` | `2` | Concurrent eval runs. Requests above the cap get a 429. |
| `RLAB_CORS_ORIGINS` | `["http://localhost:3102", …]` | Allowed browser origins |
| `RLAB_LOG_LEVEL` / `RLAB_LOG_JSON` | `INFO` / `false` | structlog output |
| `RLAB_API_URL` (web) | `http://127.0.0.1:8102` | Where Next.js proxies `/api/*` |

### Pipeline configs

Pipelines live in [`data/pipelines/*.json`](data/pipelines) and are validated by a Pydantic discriminated union:

```json
{
  "name": "hybrid-rerank",
  "description": "Hybrid RRF candidates re-scored by an MS MARCO MiniLM cross-encoder.",
  "spec": {
    "kind": "hybrid_rerank",
    "top_k": 10,
    "bm25_k": 50,
    "dense_k": 50,
    "rrf_k": 60,
    "rerank_candidates": 30,
    "query_rewrite": null,
    "generation": { "max_context_chunks": 5, "abstain_below": 0.2 }
  }
}
```

`kind` is one of `bm25`, `dense`, `hybrid` or `hybrid_rerank`. Hybrid kinds also accept `bm25_weight`, `dense_weight` and `ef_search`. Any kind can take `query_rewrite: { "apply_to": "bm25" | "dense" | "both", "rerank_query": "original" | "rewritten" }`. Run `rlab configs sync`, or create a new version in the dashboard.

## What the numbers mean

| Metric | Definition |
|---|---|
| **Recall@k** | Share of the evidence span covered by the top k chunks |
| **MRR** | 1 / rank of the first chunk covering at least 50% of the evidence |
| **nDCG@k** | DCG of the marginal coverage gains, divided by a greedy ideal ordering over every overlapping chunk |
| **Context precision** | RAGAS-style. The judge marks each top-k passage useful or not against the reference answer, and the score is average precision over those marks. Full runs only. |
| **Faithfulness** | Share of answer claims the judge finds supported by the cited context |
| **Answer relevance** | Judge score for how directly the answer addresses the question |
| **Citation accuracy** | Share of `[n]` citations that point at a chunk overlapping the evidence |
| **Abstention accuracy** / **False abstention** | Correctly declining out-of-scope questions, and wrongly declining answerable ones (lower is better) |

- The run's `k` is the retrieval depth. An eval at k = 40 retrieves 40 chunks, and widens the hybrid candidate pools if needed.
- **Offline faithfulness is a proxy.** With the fake LLM, the generator adds an unsupported sentence when its cited passage covers under half of the question's terms, and the fake judge detects that sentence lexically. Offline, faithfulness therefore tracks retrieval coverage, not answer quality.
- **The gate is pinned to its runtime.** Baselines must be produced by the same runtime as the gate. After changing models or dependencies, run `rlab seed` (or `rlab eval baseline --config <name>`) on that runtime and commit the new files in `data/baselines/`.

## API overview

Interactive docs are at `http://127.0.0.1:8102/docs`. All routes are under `/api`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | DB status, offline flag, active models, chunk count |
| `GET` | `/corpus` | Documents and chunk counts |
| `GET` | `/chunks/{chunk_id}` | One chunk with its document and character span |
| `POST` | `/query` | Ask a question with a config. Returns answer, citations, retrieval, timings and cost. |
| `GET` `POST` | `/configs` | List or register pipeline configs (a new spec becomes a new version) |
| `GET` | `/configs/{ref}` · `/configs/{name}/history` | Resolve `name`, `name@version` or id · quality across versions |
| `GET` `POST` | `/golden` | List (by status) or create golden questions |
| `PATCH` | `/golden/{id}` | Edit, accept or reject |
| `POST` | `/golden/synthesize` | Generate synthetic questions into the review queue |
| `GET` `POST` | `/runs` | List runs, or start one (`202`, runs in the background, capped by `RLAB_MAX_ACTIVE_RUNS`) |
| `GET` | `/runs/{id}` · `/runs/{id}/results` · `/runs/{id}/results/{question_id}` | Summary · paginated per-question rows · full drill-down with highlights |
| `GET` | `/runs/{id}/gate` | Gate verdict against the config's baseline |
| `GET` | `/compare?baseline=…&candidate=…` | Metric deltas, drift, and per-question nDCG changes |
| `POST` | `/baselines` | Promote a completed full run to baseline |
| `GET` | `/leaderboard` | Latest completed run for each config, with gate status |
| `GET` `POST` | `/judge/calibration` | Latest calibration report, or run a new one |

Errors use a single envelope, and every response carries an `x-request-id`.

## Request and response examples

Captured from the seeded offline stack. Long fields are trimmed with `…`.

**Ask a question** with the default `hybrid-rerank` config:

```bash
curl -s http://127.0.0.1:8102/api/query \
  -H 'content-type: application/json' \
  -d '{"question": "Who presides when the President is tried for impeachment?", "config": "hybrid-rerank"}'
```

```json
{
  "config": { "name": "hybrid-rerank", "version": 2, "kind": "hybrid_rerank", "is_latest": true, "…": "…" },
  "result": {
    "answer": {
      "text": "When the President of the United States is tried, the Chief Justice shall preside: And no Person shall be convicted without the Concurrence of two thirds of the Members present. [1] The Senate shall have the sole Power to try all Impeachments. [1]",
      "citations": [
        { "marker": 1, "chunk_id": "us-constitution:0006", "document_title": "The Constitution of the United States", "heading": "Article 1", "snippet": "The Vice-President of the United States shall be President of the Senate, …" }
      ],
      "abstained": false,
      "top_evidence_score": 0.9994,
      "model": "fake-extractive-v1"
    },
    "retrieval": {
      "chunks": [
        {
          "chunk_id": "us-constitution:0006", "rank": 1, "char_start": 3443, "char_end": 4073,
          "stage_scores": { "bm25": 15.81, "dense": 0.764, "rrf": 0.0328, "rerank": 0.9994 },
          "stage_ranks": { "bm25": 1, "dense": 1, "rrf": 1, "rerank": 1 },
          "…": "…"
        }
      ]
    },
    "timings_ms": { "bm25": 497.7, "embed": 503.4, "dense": 18.7, "fusion": 0.07, "rerank": 2361.4, "generate": 0.4, "total": 2892.3 },
    "usage": { "generate": { "input_tokens": 1062, "output_tokens": 62, "cost_usd": 0.002744 } }
  },
  "total_cost_usd": 0.002744
}
```

The cost is what those tokens would cost on `RLAB_COST_REFERENCE_MODEL`; the offline model itself is free.

**An out-of-scope question** abstains before any model call:

```json
{
  "text": "The best evidence found was too weak to answer reliably.",
  "abstained": true,
  "abstain_reason": "low_evidence",
  "top_evidence_score": 0.00002,
  "model": null
}
```

**Compare two runs** (`GET /api/compare?baseline=<hybrid-rerank run>&candidate=<bm25 run>`), the same diff the gate makes:

```json
{
  "gate": {
    "passed": false,
    "comparable": true,
    "baseline_label": "hybrid-rerank@2 · 34cc5885",
    "candidate_label": "bm25@1 · cb6784e2",
    "tolerance": { "ndcg_at_k": 0.02, "faithfulness": 0.03 },
    "deltas": [
      { "metric": "ndcg_at_k", "baseline": 0.8902, "candidate": 0.8009, "delta": -0.0893, "tolerance": 0.02, "regressed": true },
      { "metric": "faithfulness", "baseline": 0.9375, "candidate": 0.95, "delta": 0.0125, "tolerance": 0.03, "regressed": false },
      "…"
    ],
    "drift": [{ "field": "spec_hash", "baseline": "7eae32fea567", "candidate": "5cd9fc34017b", "blocking": false }]
  },
  "questions": ["…per-question nDCG changes…"]
}
```

`comparable` turns false when the models, `k` or the golden set differ; then `passed` says nothing and the CLI gate exits 2.

**Errors** share one envelope:

```json
{ "error": { "code": "not_found", "message": "No pipeline config named 'nope'" } }
```

## Testing

```bash
make test lint typecheck build   # pytest + vitest · ruff + eslint · mypy --strict + tsc · next build
cd web && pnpm e2e               # Playwright smoke tests against a running, seeded stack
make gate                        # the quality gate
```

- **Backend:** 113 tests. Unit tests cover metrics, RRF, kappa, chunker, citations, baseline diff, evidence location, the fake LLM, and the Anthropic retry logic. Integration tests run against a real Postgres with pgvector and cover the pipeline, the eval runner (including a failing judge), the API (auth, 429, 409 and 422 paths), and CliRunner exit codes for the gate (0, 1 and 2).
- **Web:** 27 Vitest + React Testing Library tests for the API client, formatting, the playground, cited answers, the waterfall and the config dialog, plus 6 Playwright flows end to end.

## Project structure

```text
retrieval-lab/
├── backend/
│   ├── src/retrieval_lab/
│   │   ├── api/              # FastAPI app, routers, schemas, mappers, deps
│   │   ├── ingest/           # loader, heading-aware chunker, embedder
│   │   ├── retrieval/        # PipelineConfig union, BM25/dense/RRF/rerank/rewrite, pipeline
│   │   ├── generation/       # prompt assembly, citation parser, abstention
│   │   ├── evals/            # metrics, judge, kappa, calibration, runner, baseline diff, synth
│   │   ├── llm/              # provider protocol, Anthropic, offline fake, pricing
│   │   ├── repositories/     # chunks (BM25 SQL), configs, golden, runs, documents
│   │   ├── db/               # SQLAlchemy models, async session
│   │   ├── cli.py            # rlab Typer app
│   │   ├── seed.py           # one-shot demo data
│   │   └── settings.py       # pydantic-settings
│   ├── migrations/           # Alembic (schema, BM25 stats, doc length)
│   ├── tests/{unit,integration}/
│   └── requirements.lock     # pip constraints used everywhere
├── web/
│   ├── src/app/              # App Router pages: /, runs, compare, playground, golden, judge, configs
│   ├── src/components/       # views, metrics, playground, runs, golden, shell, ui (shadcn)
│   ├── src/lib/api/          # typed client, zod schemas, TanStack Query hooks
│   ├── src/proxy.ts          # adds the bearer token server-side
│   └── e2e/                  # Playwright smoke tests
├── data/
│   ├── corpus/               # 6 public-domain books (Gutenberg + US Constitution)
│   ├── pipelines/            # versioned config specs
│   ├── golden/               # seed.jsonl (62) + judge_calibration.jsonl (26)
│   └── baselines/            # gate baselines, one per config
├── scripts/                  # local-pg.sh (Postgres + pgvector, no Docker), build_corpus.py
├── docker-compose.yml
└── Makefile
```

## Roadmap

- [ ] Chunking strategies as part of the versioned config (sentence windows, parent and child chunks), so they can be compared in the leaderboard
- [ ] Learned fusion weights tuned against the golden set, with a held-out split to avoid overfitting
- [ ] Bootstrap confidence intervals on metric deltas, so the gate can test significance as well as tolerance
- [ ] Streaming answers in the playground
- [ ] Multi-judge agreement (Claude vs a second judge) alongside the human calibration
- [ ] Pluggable vector backends behind the `Retriever` protocol for comparison

## License

[MIT](LICENSE). The bundled corpus is public domain: Project Gutenberg texts and the Constitution of the United States.
