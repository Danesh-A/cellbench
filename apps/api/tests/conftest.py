"""Pytest fixtures.

Tests run against an in-memory SQLite database with a translated schema
(JSONB → JSON, UUID → CHAR). For the broader suite we recommend running
against the docker-compose Postgres so the migration is exercised; this
config is for fast unit tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("S3_ENDPOINT_URL", "")  # disable S3 calls in unit tests

from cellbench_api.db import Base, get_db  # noqa: E402
from cellbench_api.main import app  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(eng, "connect")
    def _fk_on(conn, _):  # type: ignore[no-untyped-def]
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def db_session(engine) -> Iterator:
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session) -> Iterator[TestClient]:
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
