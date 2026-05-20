# CellBench — Design Document

> A self-hosted benchmarking platform for single-cell perturbation prediction
> models. Researchers register datasets, define benchmarks, submit model
> predictions, get scored automatically, and watch a public leaderboard.

This document is the source of truth for the project's architecture and the
decisions behind it. It is written to demonstrate how I would scope, design,
and ship the kind of internal-tooling platform Arc Institute is hiring for in
the **Full Stack Engineer** role.

---

## 1. Why this project

The Arc job description names four flagship surfaces. CellBench is one
cohesive product that exercises three of them.

| Arc bullet                                                                                       | How CellBench covers it                                                                                                              |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Own and evolve the **Virtual Cell Challenge backend** — auth, metrics pipelines, analytics       | The whole product is a Virtual Cell Challenge-style benchmark: JWT auth, async scoring pipeline, per-submission analytics dashboard. |
| Architect a **Data Catalog** for browsing, searching, and interacting with rich datasets         | First-class `/datasets` browser over h5ad/AnnData, faceted search, per-dataset detail with metadata and a preview of cell counts.    |
| Build tooling to support **ML engineering workflows** — model registries, experiment tracking    | `models` + `model_versions` tables form a registry; every submission is a tracked run with parameters, artifact pointer, and metrics. |
| Backend services for Arc's **Imaging platform**                                                  | Out of scope for v1 — covered in §10 (Roadmap) as a natural extension once the storage abstraction is in place.                      |


## 2. User stories

**As a researcher (challenge participant)**

1. I sign up, browse open challenges, and pick one.
2. I download the public training data and the held-out evaluation manifest.
3. I run my model locally and upload predictions as an h5ad file.
4. Within minutes I see a score for my submission against the held-out cells
   and where I rank on the leaderboard.
5. I track all of my submissions in one place, with the model and parameters
   that produced each.

**As a challenge organizer (Arc scientist)**

1. I register a new dataset in the catalog by pointing at an h5ad in our
   object store and filling in metadata (organism, modality, perturbations).
2. I create a challenge that references a dataset, defines train/eval splits,
   chooses a scoring metric, and sets a deadline.
3. I monitor submission volume, leaderboard movement, and median time-to-score
   from an analytics page.

**As an ML engineer (internal)**

1. I register a model in the registry, push successive `model_versions` as I
   iterate, and link each version to the submissions it produced.
2. I can answer "what was the best model on Challenge X last month and what
   parameters did it use" with one query.

## 3. System architecture

```
┌────────────┐        ┌─────────────────┐        ┌──────────────┐
│  Next.js   │ ──────▶│   FastAPI API   │◀──────▶│  PostgreSQL  │
│  (web)     │  HTTP  │   (api)         │  SQL   │              │
└────────────┘        └────────┬────────┘        └──────────────┘
                               │
                  enqueue      │   read/write
                  submission   ▼   artifacts
                       ┌──────────────┐         ┌──────────────┐
                       │  Scorer      │◀───────▶│   MinIO /    │
                       │  (worker)    │   S3    │   S3         │
                       └──────────────┘         └──────────────┘
```

Four services, each in its own container, wired by docker-compose locally and
deployable to any container runtime.

- **web** — Next.js 14 App Router, TypeScript, Tailwind. Server components
  for catalog pages, client components for the submission flow.
- **api** — FastAPI on Python 3.12. Stateless, horizontally scalable. Owns
  auth, persistence, signed-URL minting, and submission orchestration.
- **scorer** — Long-running Python worker. Polls a `submissions` queue
  (Postgres `SELECT … FOR UPDATE SKIP LOCKED`), pulls the prediction artifact
  from object storage, computes metrics against the held-out ground truth,
  and writes a `score_runs` row.
- **storage** — S3-compatible object store (MinIO locally, GCS/S3 in prod).
  Holds h5ad datasets, submission predictions, and ground-truth artifacts.
  All client uploads/downloads go via pre-signed URLs minted by the API — the
  API process never streams large files.

Why Postgres for the queue instead of Redis/SQS? Three reasons:
the submission table is the source of truth either way; SKIP LOCKED gives
us competing-consumer semantics for free; and one fewer service to operate
is worth more in v1 than the marginal throughput of a dedicated broker. The
worker interface is a single function, so swapping to SQS/PubSub later is a
half-day refactor.

## 4. Data model

```
users (id, email UNIQUE, password_hash, full_name, role, created_at)
  └─ submissions.user_id
  └─ models.owner_id

datasets (id, slug UNIQUE, name, description, organism, modality, n_cells,
          n_genes, storage_uri, extra JSONB, created_at, created_by_id)
  └─ challenges.dataset_id

challenges (id, slug UNIQUE, dataset_id, title, description_md, metric,
            eval_split JSONB, deadline, is_open, created_at)
  └─ submissions.challenge_id

models (id, owner_id, name, description, created_at)
  └─ model_versions.model_id

model_versions (id, model_id, version, framework, parameters JSONB,
                git_sha, created_at)
  └─ submissions.model_version_id

submissions (id, user_id, challenge_id, model_version_id NULLABLE,
             artifact_key, status ENUM(pending_upload|queued|scoring|scored|failed),
             submitted_at, scored_at, error_message)
  └─ score_runs.submission_id (1:1 once scored)

score_runs (id, submission_id UNIQUE, metric, score, breakdown JSONB,
            scorer_version, started_at, finished_at)
```

Notes on schema:

- **`extra JSONB` on `datasets`** — single-cell metadata is open-ended
  (perturbation list, batch info, library prep). A JSONB column with a few
  promoted/indexed keys is the right balance between flexibility and
  queryability. The promoted keys (`organism`, `modality`) are indexed
  columns exposed as faceted filters in the UI.
- **`status` ENUM with explicit transitions** —
  `pending_upload → queued → scoring → scored` or
  `pending_upload → queued → scoring → failed`. The scorer uses an atomic
  update (`UPDATE … WHERE status = 'queued' RETURNING …`) to claim work,
  which combined with SKIP LOCKED prevents double-scoring.
- **`model_version_id` is nullable** — researchers can submit ad-hoc
  predictions without registering a model first. The registry is encouraged,
  not enforced. Unregistered submissions still rank.
- **`score_runs` is separate from `submissions`** so we can re-score a
  submission with an updated scorer version without losing history.

## 5. API surface

REST + JSON. OpenAPI auto-generated by FastAPI at `/docs`.

```
POST   /v1/auth/register              { email, password, full_name }
POST   /v1/auth/login                 { email, password }  → { access_token }
GET    /v1/auth/me                                          → User

GET    /v1/datasets                   ?organism=&modality=&q=&offset=&limit=
GET    /v1/datasets/{slug}                                  → Dataset
POST   /v1/datasets                   (admin)               creates dataset

GET    /v1/challenges                 ?is_open=true|false
GET    /v1/challenges/{slug}                                → Challenge
GET    /v1/challenges/{slug}/leaderboard                    → ranked submissions
POST   /v1/challenges                 (admin)

POST   /v1/submissions                { challenge_id,
                                        model_version_id?,
                                        filename }
                                       → { submission_id, upload_url, object_key }
POST   /v1/submissions/{id}/complete  client calls after S3 PUT, transitions
                                       status to `queued`
GET    /v1/submissions/{id}                                 → Submission
GET    /v1/submissions/mine

GET    /v1/models
POST   /v1/models
POST   /v1/models/{id}/versions       { version, framework, parameters }
GET    /v1/models/{id}/versions

GET    /healthz                                             → { status, version }
```

Conventions:

- Offset-paginated list endpoints (`?offset=&limit=`) on datasets; default
  limit 50, max 200.
- JWT in `Authorization: Bearer …`. 7-day expiry. Refresh via re-login in v1.
- Errors follow FastAPI's default `{"detail": "..."}` envelope.

## 6. Submission and scoring flow

1. **Client** calls `POST /submissions` with the challenge ID and filename.
2. **API** inserts a row with `status = 'pending_upload'`, mints a pre-signed
   S3 PUT URL for `submissions/{submission_id}/{filename}`, returns both.
3. **Client** uploads the h5ad directly to object storage.
4. **Client** calls `POST /submissions/{id}/complete`. API verifies the
   object exists, transitions status to `queued`.
5. **Scorer** (one of N workers) runs a loop:
   ```sql
   UPDATE submissions
      SET status = 'scoring'
    WHERE id = (
      SELECT id FROM submissions
       WHERE status = 'queued'
       ORDER BY submitted_at
       FOR UPDATE SKIP LOCKED
       LIMIT 1
    )
    RETURNING id;
   ```
6. Worker downloads the prediction h5ad, the challenge's held-out
   `ground_truth.h5ad`, and the `basal.h5ad` control population from object
   storage. Builds a `ScoringContext` and runs the configured metric
   (`vcc_composite` by default — unweighted mean of DES, PDS, and MAE).
   Writes a `score_runs` row and transitions the submission to `scored`. On
   exception, transitions to `failed` with `error_message` and logs the
   traceback via structlog.
7. Leaderboard query joins `submissions × score_runs`, dedupes to a user's
   best score per challenge, and ranks. The query is fast on Postgres up to
   ~1M submissions per challenge; beyond that we'd materialize a view.



## 7. Frontend

Next.js 14 App Router, TypeScript, Tailwind. Server components for
content-heavy pages (catalog, challenge detail, leaderboard) so the first
paint is fast and SEO-friendly; client components for anything stateful
(submission flow, filters).

Key routes:

```
/                              landing
/login
/dashboard                     your submissions with live status and score
/datasets                      faceted browser (organism, modality, free-text)
/datasets/[slug]               dataset metadata and storage details
/challenges                    list filterable by open/closed
/challenges/[slug]             challenge description + live leaderboard
/challenges/[slug]/submit      file upload, queues submission for scoring
/models                        your registered models and versions
```


## 8. Infrastructure

- **Local** — `docker compose up` brings up postgres, minio, api, scorer,
  web. Hot reload on api (`uvicorn --reload`) and web (`next dev`).
- **CI** — GitHub Actions: ruff + mypy + pytest on api; ruff + pytest on
  scorer; tsc + eslint on web; docker build of all three images on every push.
- **Prod** — Each service is a container. The reference deployment is
  Cloud Run + Cloud SQL + GCS (matches the JD's "GCP, AWS, or Azure"
  preferred qualification).

## 9. Security and observability

- Passwords hashed with `argon2id` (passlib) — memory-hard, resistant to
  GPU brute-force attacks.
- Admin-only endpoints gated by a `role` claim in the JWT, enforced by the
  `admin_only` FastAPI dependency.
- Structured JSON logs via `structlog` on both the api and scorer processes;
  log level configurable via `LOG_LEVEL` environment variable.

## 10. Roadmap (post-v1)

- **NGS submission module** — sister app under the same auth and storage
  primitives. Sample intake form → instrument run record → FastQC summary.
  This is a "Genomics platforms" bullet and reuses ~70 % of CellBench
  infra (auth, signed URLs, JSONB metadata, status state machines).
- **Imaging platform backend** — extending the dataset model to handle OME-TIFF
  and Zarr stores; same catalog UI with a microscopy preview pane.
- **Notebook-style data exploration** on the dataset detail page (embed a
  Vitessce / scVI viewer).
- **Distributed scoring** for challenges whose metric requires a GPU
  (move from in-process compute to a Ray or Dask cluster behind the same
  worker interface).

## 10b. Real-data wiring

After the initial scaffold, CellBench was wired to Arc Institute's actual
**Virtual Cell Challenge 2025 dataset** rather than a placeholder. The
goal: when a reviewer runs `docker compose up`, they should land on a
populated catalog page and a non-empty leaderboard against real Arc
data, not a "no datasets yet" empty state.

### Data flow on first boot

1. The `api` container's startup command runs in order:
   `alembic upgrade head → seed.py → fetch_vcc_data.py → baseline_submissions.py → uvicorn`.
2. `fetch_vcc_data.py` reads from `gs://arc-institute-virtual-cell-atlas/virtual-cell-challenge/2025/`
   (Requester Pays, authenticated via the host's gcloud Application
   Default Credentials mounted into the container at
   `/root/.config/gcloud`). It downloads the three splits, then writes
   five objects into MinIO under deterministic keys:
   - `datasets/vcc-2025/{train,validation,test}.h5ad`
   - `eval/vcc-2025/ground_truth.h5ad` — the test split, per-cell, with `obs.perturbation`
   - `eval/vcc-2025/basal.h5ad` — control cells extracted from train
3. `baseline_submissions.py` computes two deterministic baselines
   (basal-mean and a shrunken-delta) against the test split, uploads
   each prediction h5ad to MinIO, scores them in-process using the same
   metric registry the worker uses, and inserts paired
   `Submission` + `ScoreRun` rows. On any subsequent boot the script
   is a no-op because both rows already exist.



### Scoring: three official metrics, not Pearson

The current `apps/scorer/cellbench_scorer/metrics.py` implements the three 
official
Virtual Cell Challenge metrics directly:

- **MAE** — reported as `1 / (1 + |pred − truth|.mean())` so larger is
  better and it shares a direction with DES and PDS.
- **PDS** — for each held-out perturbation t, count how many other
  true perturbations have a smaller Manhattan distance to `pred[t]`
  than `truth[t]` does, normalize by `n − 1`, then map to
  `1 − 2·mean_rank_fraction`. Random = 0, perfect = 1.
- **DES** — for each perturbation, identify the true DE gene set via
  Wilcoxon rank-sum (vs. basal cells) followed by Benjamini–Hochberg
  FDR at α = 0.05. The predicted DE set comes from a z-score of the
  prediction against the basal mean/variance, again BH-corrected, then
  truncated to |true| if the prediction over-flags. Score is the mean
  per-perturbation overlap `|true ∩ pred| / |true|`.
- **`vcc_composite`** — unweighted mean of the three. This is the
  default `Challenge.metric` for the seeded challenge.

`ScoringContext` is the new shared interface — metrics receive predicted
means, true means, *per-cell* truth matrices keyed by perturbation, and
the basal cell matrix. The worker assembles a `ScoringContext` from the
three h5ads (prediction + ground truth + basal) before calling the
metric. Unit tests in `apps/scorer/tests/test_metrics.py` verify each
metric is 1.0 on perfect predictions and low on random predictions.

