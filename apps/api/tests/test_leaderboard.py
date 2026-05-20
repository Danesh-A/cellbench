"""Leaderboard query semantics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellbench_api.models import (
    Challenge,
    Dataset,
    Role,
    ScoreRun,
    Submission,
    SubmissionStatus,
    User,
)
from cellbench_api.security import hash_password


def _make_user(db, email: str) -> User:
    u = User(email=email, password_hash=hash_password("x" * 12), role=Role.user)
    db.add(u)
    db.flush()
    return u


def test_leaderboard_picks_best_score_per_user(client, db_session) -> None:
    ds = Dataset(slug="ds", name="ds", storage_uri="s3://x")
    db_session.add(ds)
    db_session.flush()
    chl = Challenge(slug="c", title="c", dataset_id=ds.id, is_open=True)
    db_session.add(chl)
    db_session.flush()

    alice = _make_user(db_session, "alice@x")
    bob = _make_user(db_session, "bob@x")

    # Alice has two scored submissions: 0.4 and 0.8 (best). Bob has 0.6.
    for user, scores in [(alice, [0.4, 0.8]), (bob, [0.6])]:
        for s in scores:
            sub = Submission(
                user_id=user.id,
                challenge_id=chl.id,
                artifact_key=f"submissions/{uuid.uuid4()}/x.h5ad",
                status=SubmissionStatus.scored,
                scored_at=datetime.now(tz=UTC),
            )
            db_session.add(sub)
            db_session.flush()
            db_session.add(
                ScoreRun(submission_id=sub.id, metric="pearson_per_perturbation", score=s)
            )
    db_session.commit()

    rows = client.get("/v1/challenges/c/leaderboard").json()
    assert [r["user_email"] for r in rows] == ["alice@x", "bob@x"]
    assert rows[0]["score"] == 0.8
    assert rows[1]["score"] == 0.6
    assert [r["rank"] for r in rows] == [1, 2]
