"""Scoring worker.

Pulls one queued submission at a time using FOR UPDATE SKIP LOCKED,
downloads the prediction h5ad and the challenge's held-out ground-truth
+ basal h5ads, builds a ``ScoringContext``, and runs the configured
metric. Writes a ``ScoreRun`` row. Failures are recorded with the
exception message and the submission moves to ``failed`` status.

Layout convention in object storage:

  eval/{challenge.slug}/ground_truth.h5ad   # per-cell, with obs.perturbation
  eval/{challenge.slug}/basal.h5ad          # per-cell control population
  submissions/{submission_id}/{filename}    # the participant's prediction

Predictions are expected to be h5ad with shape ``(n_perturbations, n_genes)``
and ``adata.obs["perturbation"]`` aligned to the ground-truth labels.
"""

from __future__ import annotations

import io
import time
from datetime import UTC, datetime
from typing import Any

import anndata as ad
import numpy as np
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from cellbench_api.config import get_settings
from cellbench_api.db import SessionLocal
from cellbench_api.models import (
    Challenge,
    ScoreRun,
    Submission,
    SubmissionStatus,
)
from cellbench_api.storage import s3_client
from cellbench_scorer import __version__
from cellbench_scorer.metrics import REGISTRY, ScoringContext

log = structlog.get_logger()

POLL_INTERVAL_S = 2.0


def claim_next(db: Session) -> Submission | None:
    """Atomically claim one queued submission. Postgres only."""
    row = db.execute(
        text(
            """
            UPDATE submissions
               SET status = 'scoring'
             WHERE id = (
                 SELECT id FROM submissions
                  WHERE status = 'queued'
                  ORDER BY submitted_at
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
             )
            RETURNING id
            """
        )
    ).first()
    db.commit()
    if row is None:
        return None
    return db.get(Submission, row[0])


def _load_anndata_from_s3(key: str) -> ad.AnnData:
    settings = get_settings()
    obj = s3_client().get_object(Bucket=settings.s3_bucket, Key=key)
    buf = io.BytesIO(obj["Body"].read())
    return ad.read_h5ad(buf)


def _dense(x: Any) -> np.ndarray:
    """Force AnnData X to a dense ndarray. Sparse matrices get .toarray()."""
    if hasattr(x, "toarray"):
        return np.asarray(x.toarray())
    return np.asarray(x)


def _per_perturbation_cells(
    adata: ad.AnnData, label_col: str = "perturbation"
) -> dict[str, np.ndarray]:
    """Group cells by perturbation label. Returns label -> (n_cells, n_genes)."""
    if label_col not in adata.obs.columns:
        raise ValueError(f"ground-truth h5ad missing obs['{label_col}']")
    out: dict[str, np.ndarray] = {}
    X = _dense(adata.X)
    labels = adata.obs[label_col].astype(str).to_numpy()
    for lbl in np.unique(labels):
        out[str(lbl)] = X[labels == lbl]
    return out


def _build_context(
    pred: ad.AnnData, truth: ad.AnnData, basal: ad.AnnData
) -> ScoringContext:
    """Assemble a ScoringContext from the three input AnnData objects."""
    truth_by_pert = _per_perturbation_cells(truth)

    # Per-perturbation true means, sorted by label for determinism.
    truth_labels = sorted(truth_by_pert.keys())
    truth_mean = np.stack([truth_by_pert[lbl].mean(axis=0) for lbl in truth_labels])

    # Align prediction rows to the truth labels.
    if "perturbation" in pred.obs.columns:
        pred_labels = pred.obs["perturbation"].astype(str).tolist()
        pred_X = _dense(pred.X)
        # Reorder pred rows to match truth_labels order; missing labels error out.
        label_to_idx = {lbl: i for i, lbl in enumerate(pred_labels)}
        try:
            idx = [label_to_idx[lbl] for lbl in truth_labels]
        except KeyError as e:
            raise ValueError(f"prediction missing perturbation: {e}") from e
        pred_X = pred_X[idx]
        pred_labels = truth_labels
    else:
        # Predictions without perturbation labels are assumed to be in the
        # same order as the sorted truth labels.
        if pred.shape[0] != len(truth_labels):
            raise ValueError(
                f"prediction has {pred.shape[0]} rows but ground truth has "
                f"{len(truth_labels)} perturbations"
            )
        pred_X = _dense(pred.X)
        pred_labels = list(truth_labels)

    return ScoringContext(
        pred=pred_X,
        truth_mean=truth_mean,
        pred_labels=pred_labels,
        truth_labels=truth_labels,
        truth_cells=truth_by_pert,
        basal_cells=_dense(basal.X),
    )


def _eval_keys(challenge: Challenge) -> tuple[str, str]:
    return (
        f"eval/{challenge.slug}/ground_truth.h5ad",
        f"eval/{challenge.slug}/basal.h5ad",
    )


def score_submission(db: Session, sub: Submission) -> None:
    challenge = db.get(Challenge, sub.challenge_id)
    if challenge is None:
        raise RuntimeError(f"challenge {sub.challenge_id} not found for submission {sub.id}")

    metric_fn = REGISTRY.get(challenge.metric)
    if metric_fn is None:
        raise RuntimeError(f"unknown metric: {challenge.metric}")

    log.info("scoring", submission_id=str(sub.id), metric=challenge.metric)

    truth_key, basal_key = _eval_keys(challenge)
    pred = _load_anndata_from_s3(sub.artifact_key)
    truth = _load_anndata_from_s3(truth_key)
    basal = _load_anndata_from_s3(basal_key)

    ctx = _build_context(pred, truth, basal)
    score, breakdown = metric_fn(ctx)

    db.add(
        ScoreRun(
            submission_id=sub.id,
            metric=challenge.metric,
            score=score,
            breakdown=breakdown,
            scorer_version=__version__,
            finished_at=datetime.now(tz=UTC),
        )
    )
    sub.status = SubmissionStatus.scored
    sub.scored_at = datetime.now(tz=UTC)
    db.commit()
    log.info("scored", submission_id=str(sub.id), score=score)


def run_forever() -> None:
    settings = get_settings()
    log.info("scorer_start", env=settings.env, version=__version__)
    while True:
        try:
            with SessionLocal() as db:
                sub = claim_next(db)
                if sub is None:
                    time.sleep(POLL_INTERVAL_S)
                    continue
                try:
                    score_submission(db, sub)
                except Exception as e:
                    log.exception("score_failed", submission_id=str(sub.id))
                    sub.status = SubmissionStatus.failed
                    sub.error_message = str(e)
                    db.commit()
        except Exception:  # pragma: no cover — outer safety net
            log.exception("worker_loop_error")
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    run_forever()
