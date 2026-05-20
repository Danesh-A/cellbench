"""Pydantic schemas — the API's request/response contract.

Kept in one file so the contract is easy to scan. Field names match the
ORM model attribute names where possible.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from cellbench_api.models import Role, SubmissionStatus


# ---------- Auth -----------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: Role
    created_at: datetime


# ---------- Datasets -------------------------------------------------------


class DatasetCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=120)
    name: str
    description: str = ""
    organism: str | None = None
    modality: str | None = None
    n_cells: int | None = None
    n_genes: int | None = None
    storage_uri: str
    extra: dict[str, Any] = Field(default_factory=dict)


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    name: str
    description: str
    organism: str | None
    modality: str | None
    n_cells: int | None
    n_genes: int | None
    storage_uri: str
    extra: dict[str, Any]
    created_at: datetime


# ---------- Challenges -----------------------------------------------------


class ChallengeCreate(BaseModel):
    slug: str
    title: str
    description_md: str = ""
    dataset_id: uuid.UUID
    metric: str = "pearson_per_perturbation"
    eval_split: dict[str, Any] = Field(default_factory=dict)
    deadline: datetime | None = None


class ChallengeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slug: str
    title: str
    description_md: str
    dataset_id: uuid.UUID
    metric: str
    eval_split: dict[str, Any]
    deadline: datetime | None
    is_open: bool
    created_at: datetime


class LeaderboardRow(BaseModel):
    rank: int
    user_id: uuid.UUID
    user_email: str
    submission_id: uuid.UUID
    score: float
    scored_at: datetime
    model_name: str | None
    model_version: str | None


# ---------- Submissions ----------------------------------------------------


class SubmissionCreate(BaseModel):
    challenge_id: uuid.UUID
    model_version_id: uuid.UUID | None = None
    filename: str = Field(pattern=r"^[\w.\-]+\.h5ad$")


class SubmissionCreateResponse(BaseModel):
    submission_id: uuid.UUID
    upload_url: str
    object_key: str


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    challenge_id: uuid.UUID
    model_version_id: uuid.UUID | None
    status: SubmissionStatus
    submitted_at: datetime
    scored_at: datetime | None
    error_message: str | None


# ---------- Model registry -------------------------------------------------


class ModelCreate(BaseModel):
    name: str
    description: str = ""


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str
    created_at: datetime


class ModelVersionCreate(BaseModel):
    version: str
    framework: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    git_sha: str | None = None


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version: str
    framework: str | None
    parameters: dict[str, Any]
    git_sha: str | None
    created_at: datetime
