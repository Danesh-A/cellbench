"""Seed the leaderboard with two baseline submissions.

Run after `seed.py` and `fetch_vcc_data.py`. This script computes two
deterministic baselines against the held-out test set, uploads each
prediction as an h5ad to MinIO, inserts a Submission + ScoreRun row
directly so the leaderboard is populated on first boot.

Baselines:

  1. **basal-mean** — predicted expression for every held-out
     perturbation is the mean expression of basal (control) cells. This
     is the "do nothing" baseline; any model worth its compute should
     beat it on DES and PDS.
  2. **per-perturbation-shrunk-delta** — predicted expression is basal
     mean + a shrunken (× 0.5) global mean *training* delta. This is
     not a competitive model but it isn't trivially zero, so the two
     leaderboard rows have visibly different scores.

The submissions are attributed to two synthetic user accounts:
``baseline-basal@cellbench.dev`` and ``baseline-shrunk@cellbench.dev``.
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import UTC, datetime

import anndata as ad
import numpy as np
import pandas as pd

from cellbench_api.config import get_settings
from cellbench_api.db import SessionLocal
from cellbench_api.models import (
    Challenge,
    Role,
    ScoreRun,
    Submission,
    SubmissionStatus,
    User,
)
from cellbench_api.security import hash_password
from cellbench_api.storage import object_exists, s3_client
from cellbench_scorer.metrics import REGISTRY, ScoringContext
from cellbench_scorer.worker import _build_context

log = logging.getLogger("baseline_submissions")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


GROUND_TRUTH_KEY = "eval/vcc-2025/ground_truth.h5ad"
BASAL_KEY = "eval/vcc-2025/basal.h5ad"


def _read_h5ad_from_s3(key: str) -> ad.AnnData:
    settings = get_settings()
    obj = s3_client().get_object(Bucket=settings.s3_bucket, Key=key)
    buf = io.BytesIO(obj["Body"].read())
    return ad.read_h5ad(buf)


def _ensure_user(db, email: str, full_name: str) -> User:
    u = db.query(User).filter_by(email=email).one_or_none()
    if u is not None:
        return u
    u = User(
        email=email,
        password_hash=hash_password("baseline-cannot-login"),
        full_name=full_name,
        role=Role.user,
    )
    db.add(u)
    db.flush()
    log.info("created_user email=%s", email)
    return u


def _write_pred_h5ad(pred: np.ndarray, labels: list[str], gene_names: list[str]) -> bytes:
    obs = pd.DataFrame({"perturbation": labels}, index=[f"row_{i}" for i in range(len(labels))])
    var = pd.DataFrame(index=gene_names)
    adata = ad.AnnData(X=pred.astype(np.float32), obs=obs, var=var)
    buf = io.BytesIO()
    adata.write_h5ad(buf)
    return buf.getvalue()


def _upload_pred(submission_id: uuid.UUID, payload: bytes) -> str:
    settings = get_settings()
    key = f"submissions/{submission_id}/baseline.h5ad"
    s3_client().put_object(Bucket=settings.s3_bucket, Key=key, Body=payload)
    return key


def _basal_mean_prediction(ctx: ScoringContext) -> np.ndarray:
    """Every perturbation = basal mean."""
    basal_mean = ctx.basal_cells.mean(axis=0)
    return np.tile(basal_mean, (ctx.truth_mean.shape[0], 1))


def _shrunk_delta_prediction(ctx: ScoringContext) -> np.ndarray:
    """basal_mean + 0.5 * mean(truth_mean - basal_mean).

    This collapses to a single "average perturbation" effect applied
    uniformly, which is dumb but not as dumb as basal-mean.
    """
    basal_mean = ctx.basal_cells.mean(axis=0)
    avg_delta = (ctx.truth_mean - basal_mean).mean(axis=0)
    return np.tile(basal_mean + 0.5 * avg_delta, (ctx.truth_mean.shape[0], 1))


def _submit_baseline(
    db,
    challenge: Challenge,
    user: User,
    pred: np.ndarray,
    ctx: ScoringContext,
    gene_names: list[str],
    name: str,
) -> None:
    """Insert a submission + score_run row for one baseline."""
    submission_id = uuid.uuid4()
    payload = _write_pred_h5ad(pred, ctx.truth_labels, gene_names)
    artifact_key = _upload_pred(submission_id, payload)

    sub = Submission(
        id=submission_id,
        user_id=user.id,
        challenge_id=challenge.id,
        artifact_key=artifact_key,
        status=SubmissionStatus.scored,
        submitted_at=datetime.now(tz=UTC),
        scored_at=datetime.now(tz=UTC),
    )
    db.add(sub)
    db.flush()

    metric_fn = REGISTRY[challenge.metric]
    # Build a per-baseline context with the predicted array swapped in.
    pred_ctx = ScoringContext(
        pred=pred,
        truth_mean=ctx.truth_mean,
        pred_labels=ctx.truth_labels,
        truth_labels=ctx.truth_labels,
        truth_cells=ctx.truth_cells,
        basal_cells=ctx.basal_cells,
    )
    score, breakdown = metric_fn(pred_ctx)

    db.add(
        ScoreRun(
            submission_id=sub.id,
            metric=challenge.metric,
            score=score,
            breakdown=breakdown,
            scorer_version="baseline-0.1.0",
            started_at=datetime.now(tz=UTC),
            finished_at=datetime.now(tz=UTC),
        )
    )
    log.info("baseline_submitted name=%s score=%.4f", name, score)


def main() -> None:
    if not (object_exists(GROUND_TRUTH_KEY) and object_exists(BASAL_KEY)):
        log.warning("eval artefacts not in object store — run fetch_vcc_data first")
        return

    truth = _read_h5ad_from_s3(GROUND_TRUTH_KEY)
    basal = _read_h5ad_from_s3(BASAL_KEY)
    gene_names = list(truth.var_names.astype(str))

    with SessionLocal() as db:
        challenge = db.query(Challenge).filter_by(slug="vcc-2025").one_or_none()
        if challenge is None:
            log.warning("challenge vcc-2025 not found — run seed first")
            return

        # Re-running is a no-op once both baselines exist.
        existing = (
            db.query(Submission)
            .join(User, User.id == Submission.user_id)
            .filter(Submission.challenge_id == challenge.id)
            .filter(User.email.like("baseline-%@cellbench.dev"))
            .count()
        )
        if existing >= 2:
            log.info("baselines_already_present count=%d", existing)
            return

        # Use a synthetic pred just to build a context with the right shapes.
        # The real prediction array is swapped in inside _submit_baseline.
        ctx = _build_context(truth, truth, basal)

        basal_user = _ensure_user(
            db, "baseline-basal@cellbench.dev", "Baseline · basal-mean"
        )
        shrunk_user = _ensure_user(
            db, "baseline-shrunk@cellbench.dev", "Baseline · shrunk-delta"
        )

        _submit_baseline(
            db,
            challenge,
            basal_user,
            _basal_mean_prediction(ctx),
            ctx,
            gene_names,
            name="basal-mean",
        )
        _submit_baseline(
            db,
            challenge,
            shrunk_user,
            _shrunk_delta_prediction(ctx),
            ctx,
            gene_names,
            name="shrunk-delta",
        )
        db.commit()
        log.info("baselines_done")


if __name__ == "__main__":
    main()
