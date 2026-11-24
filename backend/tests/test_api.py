"""HTTP tests (Goals 1 and 9, INV-7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.config import Settings

BASE = datetime(2026, 11, 1, tzinfo=UTC)


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_list_returns_only_own_tasks_newest_first(client, make_task):
    older = await make_task(created_at=BASE)
    newer = await make_task(created_at=BASE + timedelta(minutes=1))
    await make_task(user_id="other-user", created_at=BASE + timedelta(minutes=2))

    response = await client.get("/tasks")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [i["id"] for i in items] == [str(newer.id), str(older.id)]
    assert all("user_id" not in i for i in items)


async def test_list_is_capped_at_50(client, make_task):
    for n in range(51):
        await make_task(created_at=BASE + timedelta(seconds=n))
    response = await client.get("/tasks")
    assert len(response.json()["items"]) == 50


async def test_get_own_task(client, make_task):
    task = await make_task(module="cbtf", kind="book")
    response = await client.get(f"/tasks/{task.id}")
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["version"], body["module"]) == ("ready", 1, "cbtf")


async def test_other_users_task_and_unknown_id_are_404(client, make_task):
    other = await make_task(user_id="other-user")
    for task_id in (other.id, uuid.uuid4()):
        response = await client.get(f"/tasks/{task_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "task not found"}


async def test_non_uuid_id_is_422(client):
    assert (await client.get("/tasks/not-a-uuid")).status_code == 422


async def test_without_identity_task_routes_are_401(make_client, database_url, engine):
    settings = Settings(
        _env_file=None, app_env="test", dev_identity_enabled=False, database_url=database_url
    )
    async with make_client(settings) as client:
        for path in ("/tasks", f"/tasks/{uuid.uuid4()}"):
            response = await client.get(path)
            assert response.status_code == 401
            assert response.json() == {"detail": "not authenticated"}
            assert response.headers["www-authenticate"] == "Bearer"
        assert (await client.get("/health")).status_code == 200
