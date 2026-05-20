"""Challenge endpoints and leaderboard query."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from cellbench_api.db import get_db
from cellbench_api.deps import admin_only
from cellbench_api.models import (
    Challenge,
    Dataset,
    Model,
    ModelVersion,
    ScoreRun,
    Submission,
    SubmissionStatus,
    User,
)
from cellbench_api.schemas import ChallengeCreate, ChallengeOut, LeaderboardRow

router = APIRouter()


@router.get("", response_model=list[ChallengeOut])
def list_challenges(
    db: Annotated[Session, Depends(get_db)],
    is_open: bool | None = None,
) -> list[Challenge]:
    stmt = select(Challenge).order_by(Challenge.created_at.desc())
    if is_open is not None:
        stmt = stmt.where(Challenge.is_open == is_open)
    return list(db.scalars(stmt))


@router.get("/{slug}", response_model=ChallengeOut)
def get_challenge(slug: str, db: Annotated[Session, Depends(get_db)]) -> Challenge:
    chl = db.scalar(
        select(Challenge).where(Challenge.slug == slug).options(selectinload(Challenge.dataset))
    )
    if chl is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return chl


@router.get("/{slug}/leaderboard", response_model=list[LeaderboardRow])
def leaderboard(
    slug: str,
    db: Annotated[Session, Depends(get_db)],
    limit: int = 100,
) -> list[LeaderboardRow]:
    """Return one row per user, with their best scored submission."""
    chl = db.scalar(select(Challenge).where(Challenge.slug == slug))
    if chl is None:
        raise HTTPException(status_code=404, detail="Challenge not found")

    # Pull the best score per user via a window or a max-per-group join.
    # We do it in Python here for clarity; with >100k submissions move to
    # a materialized view (see DESIGN.md §6).
    rows = db.execute(
        select(Submission, ScoreRun, User, Model, ModelVersion)
        .join(ScoreRun, ScoreRun.submission_id == Submission.id)
        .join(User, User.id == Submission.user_id)
        .join(ModelVersion, ModelVersion.id == Submission.model_version_id, isouter=True)
        .join(Model, Model.id == ModelVersion.model_id, isouter=True)
        .where(Submission.challenge_id == chl.id)
        .where(Submission.status == SubmissionStatus.scored)
        .order_by(ScoreRun.score.desc())
    ).all()

    seen: set[str] = set()
    out: list[LeaderboardRow] = []
    for sub, sr, user, model, mv in rows:
        if str(user.id) in seen:
            continue
        seen.add(str(user.id))
        out.append(
            LeaderboardRow(
                rank=len(out) + 1,
                user_id=user.id,
                user_email=user.email,
                submission_id=sub.id,
                score=sr.score,
                scored_at=sub.scored_at or sr.finished_at,
                model_name=model.name if model else None,
                model_version=mv.version if mv else None,
            )
        )
        if len(out) >= limit:
            break
    return out


@router.post(
    "",
    response_model=ChallengeOut,
    status_code=201,
    dependencies=[Depends(admin_only)],
)
def create_challenge(
    body: ChallengeCreate, db: Annotated[Session, Depends(get_db)]
) -> Challenge:
    if db.scalar(select(Challenge).where(Challenge.slug == body.slug)) is not None:
        raise HTTPException(status_code=409, detail="Slug already in use")
    if db.get(Dataset, body.dataset_id) is None:
        raise HTTPException(status_code=400, detail="dataset_id does not exist")
    chl = Challenge(**body.model_dump())
    db.add(chl)
    db.flush()
    return chl
