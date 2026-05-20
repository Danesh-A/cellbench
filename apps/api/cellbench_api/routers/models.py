"""Model-registry endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from cellbench_api.db import get_db
from cellbench_api.deps import current_user
from cellbench_api.models import Model, ModelVersion, User
from cellbench_api.schemas import (
    ModelCreate,
    ModelOut,
    ModelVersionCreate,
    ModelVersionOut,
)

router = APIRouter()


@router.get("", response_model=list[ModelOut])
def list_models(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> list[Model]:
    return list(
        db.scalars(
            select(Model).where(Model.owner_id == user.id).order_by(Model.created_at.desc())
        )
    )


@router.post("", response_model=ModelOut, status_code=201)
def create_model(
    body: ModelCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> Model:
    existing = db.scalar(
        select(Model).where(Model.owner_id == user.id).where(Model.name == body.name)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Model name already in use")
    model = Model(owner_id=user.id, name=body.name, description=body.description)
    db.add(model)
    db.flush()
    return model


@router.get("/{model_id}/versions", response_model=list[ModelVersionOut])
def list_versions(
    model_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> list[ModelVersion]:
    model = db.get(Model, model_id)
    if model is None or model.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Model not found")
    return list(
        db.scalars(
            select(ModelVersion)
            .where(ModelVersion.model_id == model_id)
            .order_by(ModelVersion.created_at.desc())
        )
    )


@router.post("/{model_id}/versions", response_model=ModelVersionOut, status_code=201)
def create_version(
    model_id: UUID,
    body: ModelVersionCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> ModelVersion:
    model = db.get(Model, model_id)
    if model is None or model.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Model not found")
    existing = db.scalar(
        select(ModelVersion)
        .where(ModelVersion.model_id == model_id)
        .where(ModelVersion.version == body.version)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Version already exists for this model")
    mv = ModelVersion(model_id=model_id, **body.model_dump())
    db.add(mv)
    db.flush()
    return mv
