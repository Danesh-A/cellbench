"""Submission lifecycle endpoints.

Submission flow (see DESIGN.md §6):
  1) POST /v1/submissions         → row in status `pending_upload` + presigned PUT URL
  2) Client uploads to S3
  3) POST /v1/submissions/{id}/complete → status `queued`
  4) Scorer worker picks it up    → `scoring` → `scored` | `failed`
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from cellbench_api.db import get_db
from cellbench_api.deps import current_user
from cellbench_api.models import (
    Challenge,
    Model,
    ModelVersion,
    Submission,
    SubmissionStatus,
    User,
)
from cellbench_api.schemas import (
    SubmissionCreate,
    SubmissionCreateResponse,
    SubmissionOut,
)
from cellbench_api.storage import object_exists, presign_put

router = APIRouter()


@router.post("", response_model=SubmissionCreateResponse, status_code=201)
def create_submission(
    body: SubmissionCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> SubmissionCreateResponse:
    challenge = db.get(Challenge, body.challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if not challenge.is_open:
        raise HTTPException(status_code=400, detail="Challenge is closed for submissions")

    if body.model_version_id is not None:
        mv = db.scalar(
            select(ModelVersion)
            .join(Model, Model.id == ModelVersion.model_id)
            .where(ModelVersion.id == body.model_version_id)
            .where(Model.owner_id == user.id)
        )
        if mv is None:
            raise HTTPException(status_code=400, detail="model_version_id does not exist")

    sub = Submission(
        user_id=user.id,
        challenge_id=challenge.id,
        model_version_id=body.model_version_id,
        artifact_key="",  # set below once id is known
        status=SubmissionStatus.pending_upload,
    )
    db.add(sub)
    db.flush()  # populate sub.id

    object_key = f"submissions/{sub.id}/{body.filename}"
    sub.artifact_key = object_key
    db.flush()

    return SubmissionCreateResponse(
        submission_id=sub.id,
        upload_url=presign_put(object_key, content_type="application/octet-stream"),
        object_key=object_key,
    )


@router.post("/{submission_id}/complete", response_model=SubmissionOut)
def complete_submission(
    submission_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> Submission:
    sub = db.get(Submission, submission_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.status != SubmissionStatus.pending_upload:
        raise HTTPException(
            status_code=409,
            detail=f"Submission already transitioned to {sub.status.value}",
        )
    if not object_exists(sub.artifact_key):
        raise HTTPException(status_code=400, detail="Upload not present in object storage")
    sub.status = SubmissionStatus.queued
    db.flush()
    return sub


@router.get("/mine", response_model=list[SubmissionOut])
def my_submissions(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> list[Submission]:
    return list(
        db.scalars(
            select(Submission)
            .where(Submission.user_id == user.id)
            .order_by(Submission.submitted_at.desc())
        )
    )


@router.get("/{submission_id}", response_model=SubmissionOut)
def get_submission(
    submission_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> Submission:
    sub = db.get(Submission, submission_id)
    if sub is None or sub.user_id != user.id:
        raise HTTPException(status_code=404, detail="Submission not found")
    return sub
