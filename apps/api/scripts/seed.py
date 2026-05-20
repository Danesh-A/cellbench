"""Seed the database with a demo admin, the real Arc VCC 2025 dataset,
and a single open challenge using the official three-metric composite.

Run with:
    python -m scripts.seed

This script only writes *metadata* rows. The actual h5ad bytes are
fetched separately by `scripts/fetch_vcc_data.py` and the leaderboard
is populated by `scripts/baseline_submissions.py`. All three are
idempotent and safe to re-run.
"""

from __future__ import annotations

from cellbench_api.db import SessionLocal
from cellbench_api.models import Challenge, Dataset, Role, User
from cellbench_api.security import hash_password

DATASET_SLUG = "vcc-2025"
CHALLENGE_SLUG = "vcc-2025"


def seed() -> None:
    with SessionLocal() as db:
        admin = db.query(User).filter_by(email="admin@cellbench.dev").one_or_none()
        if admin is None:
            admin = User(
                email="admin@cellbench.dev",
                password_hash=hash_password("admin"),
                full_name="Demo Admin",
                role=Role.admin,
            )
            db.add(admin)
            db.flush()
            print(f"created admin user: {admin.email}")

        dataset = db.query(Dataset).filter_by(slug=DATASET_SLUG).one_or_none()
        if dataset is None:
            dataset = Dataset(
                slug=DATASET_SLUG,
                name="Virtual Cell Challenge 2025 (Arc Institute, H1 hESC)",
                description=(
                    "Arc Institute's dedicated Virtual Cell Challenge dataset. "
                    "Single-cell perturbation responses in a human embryonic "
                    "stem cell line (H1 hESC). ~300,000 cells across 300 "
                    "carefully curated target gene perturbations, organized "
                    "into train, validation, and held-out test splits.\n\n"
                    "Source: gs://arc-institute-virtual-cell-atlas/virtual-cell-challenge/2025/  "
                    "License: CC0 1.0  "
                    "Atlas page: https://arcinstitute.org/tools/virtualcellatlas"
                ),
                organism="Homo sapiens",
                modality="scRNA-seq (Perturb-seq)",
                n_cells=300_000,
                n_genes=18_080,  # approximate; updated from h5ad headers on fetch
                storage_uri="s3://cellbench/datasets/vcc-2025/train.h5ad",
                extra={
                    "cell_line": "H1 hESC",
                    "perturbation_type": "CRISPRi",
                    "n_target_genes": 300,
                    "license": "CC0-1.0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/legalcode.txt",
                    "source_bucket": "gs://arc-institute-virtual-cell-atlas",
                    "source_prefix": "virtual-cell-challenge/2025",
                    "atlas_page": "https://arcinstitute.org/tools/virtualcellatlas",
                    "challenge_url": "https://virtualcellchallenge.org",
                    "cell_paper": "https://www.cell.com/cell/fulltext/S0092-8674(25)00675-0",
                    "splits": ["train", "validation", "test"],
                },
                created_by_id=admin.id,
            )
            db.add(dataset)
            db.flush()
            print(f"created dataset: {dataset.slug}")

        challenge = db.query(Challenge).filter_by(slug=CHALLENGE_SLUG).one_or_none()
        if challenge is None:
            challenge = Challenge(
                slug=CHALLENGE_SLUG,
                title="Virtual Cell Challenge — VCC 2025 (replay)",
                description_md=(
                    "Predict single-cell transcriptomic responses to held-out "
                    "perturbations in H1 hESC, using Arc Institute's published "
                    "[Virtual Cell Challenge 2025 dataset](https://arcinstitute.org/tools/virtualcellatlas).\n\n"
                    "**Task.** For each held-out perturbation in the test split, "
                    "submit a predicted mean transcriptome (one row per "
                    "perturbation, columns aligned to the dataset's gene index).\n\n"
                    "**Submission format.** An `.h5ad` with shape "
                    "`(n_held_out_perturbations, n_genes)` and "
                    "`obs.perturbation` listing the perturbation label for each row.\n\n"
                    "**Scoring.** The official three-metric composite:\n"
                    "- **DES** (Differential Expression Score) — Wilcoxon "
                    "rank-sum + Benjamini–Hochberg FDR\n"
                    "- **PDS** (Perturbation Discrimination Score) — "
                    "Manhattan-distance ranking\n"
                    "- **MAE** (Mean Absolute Error similarity)\n\n"
                    "Each component is in `[0, 1]`; the leaderboard ranks by "
                    "the unweighted mean. The breakdown for each submission "
                    "includes the three individual scores."
                ),
                dataset_id=dataset.id,
                metric="vcc_composite",
                eval_split={
                    "split": "test",
                    "storage_uri": "s3://cellbench/eval/vcc-2025/ground_truth.h5ad",
                    "basal_uri": "s3://cellbench/eval/vcc-2025/basal.h5ad",
                },
                is_open=True,
            )
            db.add(challenge)
            print(f"created challenge: {challenge.slug}")

        db.commit()
        print("seed complete.")


if __name__ == "__main__":
    seed()
