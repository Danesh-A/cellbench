# CellBench

A self-hosted benchmarking platform for single-cell perturbation prediction
models — Virtual Cell Challenge in a box.

Researchers register **datasets**, organizers define **challenges**, ML
engineers track **models** in a registry, and participants submit
**predictions** that are scored asynchronously and ranked on a public
**leaderboard**.

> Built as a portfolio piece for Arc Institute's Full Stack Engineer role —
> see [`DESIGN.md`](./DESIGN.md) for the full architecture rationale.

## Screenshots

| | |
|---|---|
| ![Landing page](docs/screenshots/landing.png) | ![Dataset catalog](docs/screenshots/datasets.png) |
| **Landing** — feature overview and nav | **Dataset catalog** — faceted browse with organism / modality filters |
| ![Challenge leaderboard](docs/screenshots/leaderboard.png) | ![Submit prediction](docs/screenshots/submit.png) |
| **Leaderboard** — live ranked scores with DES / PDS / MAE breakdown | **Submit** — drag-and-drop h5ad upload, queued for async scoring |


## Powered by real Arc Institute data

CellBench ships configured against **Arc's published Virtual Cell Challenge
2025 dataset** (CC0 1.0) — ~300,000 cells in a H1 hESC line across 300
target gene perturbations, with train/validation/test splits.

- **Data source:** [`gs://arc-institute-virtual-cell-atlas/virtual-cell-challenge/2025/`](https://arcinstitute.org/tools/virtualcellatlas)
- **License:** [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt)
- **Reference:** [Virtual Cell Challenge: Toward a Turing test for the virtual cell — Cell, 2025](https://www.cell.com/cell/fulltext/S0092-8674(25)00675-0)
- **Scoring:** the three official metrics implemented in `apps/scorer/cellbench_scorer/metrics.py`:
  - **DES** — Differential Expression Score (Wilcoxon rank-sum + Benjamini–Hochberg FDR)
  - **PDS** — Perturbation Discrimination Score (Manhattan-distance ranking)
  - **MAE** — Mean Absolute Error similarity
  - **`vcc_composite`** — unweighted mean of the three (the default ranking metric)

On first boot the api container fetches the dataset, registers it in the
catalog with real metadata, and submits two deterministic baselines so the
leaderboard isn't empty for visitors.

## What's in the box

| Surface          | Built on                          |
| ---------------- | --------------------------------- |
| Submission flow + leaderboard | FastAPI + Postgres + worker       |
| Dataset catalog               | Next.js, h5ad metadata, JSONB     |
| Model registry & run tracking | `models` / `model_versions` table |

## Stack

- **api** — Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- **scorer** — Python worker, AnnData / pandas / numpy / scipy, S3-compatible storage
- **web** — Next.js 14 (App Router), TypeScript, Tailwind
- **db** — PostgreSQL 16
- **storage** — MinIO locally, GCS/S3 in prod
- **infra** — docker-compose for dev; GitHub Actions CI; Cloud Run-ready

## Quickstart

### 1. Authenticate to Google Cloud (one-time)

```bash
# install gcloud CLI: https://cloud.google.com/sdk/docs/install
gcloud auth application-default login
gcloud config set project YOUR_GCP_PROJECT_ID
```

### 2. Bring it up

```bash
git clone <this repo>
cd cellbench
cp .env.example .env
docker compose up --build
```

> **Faster demo without the full dataset:** add
> `SUBSET_PERTURBATIONS=10` to your `.env` to limit the fetch to the
> first 10 perturbations. Useful on slow connections or CI.

### 3. Open

- **Web UI** — <http://localhost:3000>
- **API docs (Swagger)** — <http://localhost:8000/docs>
- **MinIO console** — <http://localhost:9001>  (`minioadmin` / `minioadmin`)
- **Postgres** — `postgres://cellbench:cellbench@localhost:5432/cellbench`
Seeded admin: `admin@cellbench.dev` / `admin`.

## Windows note: gcloud credentials path

The compose file mounts `~/.config/gcloud` into the api container. On
Windows that lives at `%APPDATA%\gcloud`. Set the env var before bringing
the stack up:

```powershell
$env:GCLOUD_CONFIG_DIR = "$env:APPDATA\gcloud"
docker compose up --build
```

Or add a permanent line to your `.env`:

```
GCLOUD_CONFIG_DIR=C:\Users\YOUR_NAME\AppData\Roaming\gcloud
```

## Project structure

```
cellbench/
├── DESIGN.md                       full design doc — read this first
├── README.md
├── docker-compose.yml
├── Makefile
├── .env.example
├── .github/workflows/ci.yml
├── apps/
│   ├── api/                        FastAPI service
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   ├── cellbench_api/
│   │   │   ├── main.py
│   │   │   ├── config.py · db.py · deps.py · security.py · storage.py
│   │   │   ├── models.py           SQLAlchemy ORM
│   │   │   ├── schemas.py          Pydantic
│   │   │   └── routers/
│   │   ├── scripts/
│   │   │   ├── seed.py             real VCC 2025 metadata
│   │   │   ├── fetch_vcc_data.py   downloads from gs://arc-institute-virtual-cell-atlas
│   │   │   └── baseline_submissions.py
│   │   └── tests/
│   ├── scorer/                     Python worker (DES/PDS/MAE + composite)
│   │   ├── pyproject.toml · Dockerfile
│   │   └── cellbench_scorer/{metrics,worker}.py
│   └── web/                        Next.js frontend
│       └── src/{app,components,lib}/
└── infra/                          deployment artifacts (stub)
```

## Development workflow

```bash
make api       # uvicorn with reload (local, not in docker)
make web       # next dev
make scorer    # run the worker against the local DB
make test      # pytest + tsc
make lint      # ruff + eslint
make migrate   # alembic upgrade head
make seed      # populate demo data
```

## Submission format

For the seeded `vcc-2025` challenge, submit an `.h5ad` with:

- `X` shape `(n_held_out_perturbations, n_genes)` — predicted mean
  transcriptome per perturbation
- `obs.perturbation` — string column with the perturbation label for
  each row (must match the labels in the held-out test split)
- `var_names` — gene names aligned with the dataset's gene index

The dashboard's drag-and-drop form handles the rest: the API mints a
pre-signed S3 PUT URL, your browser uploads directly to MinIO, the scorer
picks it up, computes DES / PDS / MAE / composite, and the leaderboard
updates.

## Roadmap

See [`DESIGN.md` §10](./DESIGN.md#10-roadmap-post-v1). The two largest
follow-ons — an NGS sample-submission module and an imaging-platform
backend — were deliberately left out of v1 to keep the product story
focused, and are designed to plug into the same auth, storage, and
schema primitives.

## License

MIT — see [`LICENSE`](./LICENSE).

## Attribution

The Virtual Cell Challenge 2025 dataset is © Arc Institute, released
under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt).
This project is not affiliated with Arc Institute.
