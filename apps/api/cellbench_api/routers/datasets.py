"""Dataset Catalog endpoints.

This is the "Data Catalog" surface from the JD. It exposes faceted
browse, detail, and admin create. Preview (cell/gene counts, obs
columns) is computed lazily from the h5ad headers by the scorer's
companion sidecar — for v1 we serve whatever was registered.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from cellbench_api.db import get_db
from cellbench_api.deps import admin_only, current_user
from cellbench_api.models import Dataset, User
from cellbench_api.schemas import DatasetCreate, DatasetOut

router = APIRouter()


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    db: Annotated[Session, Depends(get_db)],
    organism: str | None = None,
    modality: str | None = None,
    q: str | None = Query(None, description="Free-text search over name/description"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Dataset]:
    stmt = select(Dataset)
    if organism:
        stmt = stmt.where(Dataset.organism == organism)
    if modality:
        stmt = stmt.where(Dataset.modality == modality)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            (Dataset.name.ilike(like)) | (Dataset.description.ilike(like))
        )
    stmt = stmt.order_by(Dataset.created_at.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt))


@router.get("/{slug}", response_model=DatasetOut)
def get_dataset(slug: str, db: Annotated[Session, Depends(get_db)]) -> Dataset:
    ds = db.scalar(select(Dataset).where(Dataset.slug == slug))
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@router.post(
    "",
    response_model=DatasetOut,
    status_code=201,
    dependencies=[Depends(admin_only)],
)
def create_dataset(
    body: DatasetCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> Dataset:
    if db.scalar(select(Dataset).where(Dataset.slug == body.slug)) is not None:
        raise HTTPException(status_code=409, detail="Slug already in use")
    ds = Dataset(**body.model_dump(), created_by_id=user.id)
    db.add(ds)
    db.flush()
    return ds
