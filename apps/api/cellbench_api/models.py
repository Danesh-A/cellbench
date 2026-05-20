"""SQLAlchemy ORM models for CellBench.

All tables for the platform live here so the schema is reviewable in one
file. The relationships mirror the ER diagram in `DESIGN.md` §4.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cellbench_api.db import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class Role(str, enum.Enum):
    user = "user"
    admin = "admin"


class SubmissionStatus(str, enum.Enum):
    pending_upload = "pending_upload"
    queued = "queued"
    scoring = "scoring"
    scored = "scored"
    failed = "failed"


# ---------- Users ----------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), default=Role.user)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list[Submission]] = relationship(back_populates="user")
    models: Mapped[list[Model]] = relationship(back_populates="owner")


# ---------- Datasets -------------------------------------------------------


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    organism: Mapped[str | None] = mapped_column(String(120), index=True)
    modality: Mapped[str | None] = mapped_column(String(120), index=True)
    n_cells: Mapped[int | None] = mapped_column(Integer)
    n_genes: Mapped[int | None] = mapped_column(Integer)
    storage_uri: Mapped[str] = mapped_column(String(1024))
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    challenges: Mapped[list[Challenge]] = relationship(back_populates="dataset")


# ---------- Challenges -----------------------------------------------------


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description_md: Mapped[str] = mapped_column(Text, default="")
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="RESTRICT")
    )
    metric: Mapped[str] = mapped_column(String(60), default="pearson_per_perturbation")
    eval_split: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_open: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    dataset: Mapped[Dataset] = relationship(back_populates="challenges")
    submissions: Mapped[list[Submission]] = relationship(back_populates="challenge")


# ---------- Model registry -------------------------------------------------


class Model(Base):
    __tablename__ = "models"

    id: Mapped[uuid.UUID] = _pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[User] = relationship(back_populates="models")
    versions: Mapped[list[ModelVersion]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("owner_id", "name"),)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = _pk()
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("models.id", ondelete="CASCADE")
    )
    version: Mapped[str] = mapped_column(String(60))
    framework: Mapped[str | None] = mapped_column(String(60))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    git_sha: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    model: Mapped[Model] = relationship(back_populates="versions")
    submissions: Mapped[list[Submission]] = relationship(back_populates="model_version")

    __table_args__ = (UniqueConstraint("model_id", "version"),)


# ---------- Submissions & scoring ------------------------------------------


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("challenges.id", ondelete="CASCADE"), index=True
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    artifact_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, name="submission_status"),
        default=SubmissionStatus.pending_upload,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="submissions")
    challenge: Mapped[Challenge] = relationship(back_populates="submissions")
    model_version: Mapped[ModelVersion | None] = relationship(back_populates="submissions")
    score_run: Mapped[ScoreRun | None] = relationship(
        back_populates="submission", uselist=False, cascade="all, delete-orphan"
    )


class ScoreRun(Base):
    __tablename__ = "score_runs"

    id: Mapped[uuid.UUID] = _pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        unique=True,
    )
    metric: Mapped[str] = mapped_column(String(60))
    score: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    scorer_version: Mapped[str] = mapped_column(String(40), default="0.1.0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    submission: Mapped[Submission] = relationship(back_populates="score_run")
