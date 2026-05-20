"""Auth happy-path and edge cases."""

from __future__ import annotations


def test_register_then_login(client) -> None:
    r = client.post(
        "/v1/auth/register",
        json={"email": "researcher@example.com", "password": "hunter2hunter2", "full_name": "R"},
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    assert token

    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "researcher@example.com"


def test_login_wrong_password(client) -> None:
    client.post(
        "/v1/auth/register",
        json={"email": "a@b.com", "password": "abcdefgh", "full_name": ""},
    )
    r = client.post("/v1/auth/login", json={"email": "a@b.com", "password": "WRONG-WRONG"})
    assert r.status_code == 401


def test_me_requires_token(client) -> None:
    r = client.get("/v1/auth/me")
    assert r.status_code == 401
