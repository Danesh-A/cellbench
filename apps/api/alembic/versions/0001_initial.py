"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-13 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_ROLE = postgresql.ENUM("user", "admin", name="user_role", create_type=False)
SUBMISSION_STATUS = postgresql.ENUM(
    "pending_upload",
    "queued",
    "scoring",
    "scored",
    "failed",
    name="submission_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE user_role AS ENUM ('user', 'admin'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$"
        )
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE submission_status AS ENUM ('pending_upload', 'queued', 'scoring', 'scored', 'failed'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$"
        )
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("role", USER_ROLE, nullable=False, server_default="user"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        if_not_exists=True,
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True, if_not_exists=True)

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("organism", sa.String(120)),
        sa.Column("modality", sa.String(120)),
        sa.Column("n_cells", sa.Integer),
        sa.Column("n_genes", sa.Integer),
        sa.Column("storage_uri", sa.String(1024), nullable=False),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        if_not_exists=True,
    )
    op.create_index("ix_datasets_organism", "datasets", ["organism"], if_not_exists=True)
    op.create_index("ix_datasets_modality", "datasets", ["modality"], if_not_exists=True)

    op.create_table(
        "challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description_md", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "metric",
            sa.String(60),
            nullable=False,
            server_default="pearson_per_perturbation",
        ),
        sa.Column("eval_split", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("is_open", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        if_not_exists=True,
    )

    op.create_table(
        "models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("owner_id", "name"),
        if_not_exists=True,
    )

    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(60), nullable=False),
        sa.Column("framework", sa.String(60)),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("git_sha", sa.String(40)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("model_id", "version"),
        if_not_exists=True,
    )

    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "challenge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("challenges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="SET NULL"),
        ),
        sa.Column("artifact_key", sa.String(1024), nullable=False, server_default=""),
        sa.Column("status", SUBMISSION_STATUS, nullable=False, server_default="pending_upload"),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("scored_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        if_not_exists=True,
    )
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"], if_not_exists=True)
    op.create_index(
        "ix_submissions_challenge_id", "submissions", ["challenge_id"], if_not_exists=True
    )
    op.create_index("ix_submissions_status", "submissions", ["status"], if_not_exists=True)

    op.create_table(
        "score_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("metric", sa.String(60), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("breakdown", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("scorer_version", sa.String(40), nullable=False, server_default="0.1.0"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("score_runs")
    op.drop_table("submissions")
    op.drop_table("model_versions")
    op.drop_table("models")
    op.drop_table("challenges")
    op.drop_table("datasets")
    op.drop_table("users")
    SUBMISSION_STATUS.drop(op.get_bind(), checkfirst=True)
    USER_ROLE.drop(op.get_bind(), checkfirst=True)
