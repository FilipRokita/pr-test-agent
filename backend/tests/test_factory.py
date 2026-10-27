from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.factory import create_app

DATABASE_URL = "postgresql+psycopg://taskly:taskly@localhost:5432/taskly"


@pytest.fixture
def session():
    session = Mock(spec=Session)
    session.scalars.return_value = []
    return session


@pytest.fixture
def database(session):
    with (
        patch("app.core.lifespan.create_database_engine") as create_engine,
        patch("app.core.lifespan.initialize"),
        patch("app.core.lifespan.create_session_factory") as create_session_factory,
    ):
        create_session_factory.return_value = Mock(return_value=session)
        yield create_engine


def test_create_app_uses_explicit_database_url():
    with patch("app.factory.resolve_database_url", return_value=DATABASE_URL) as resolve:
        app = create_app(DATABASE_URL)
    resolve.assert_called_once_with(DATABASE_URL)
    assert app.state.database_url == DATABASE_URL
    assert app.title == "Taskly API"


def test_created_app_serves_health_and_todos_routes(database, session):
    with TestClient(create_app(DATABASE_URL)) as client:
        health = client.get("/api/health")
        todos = client.get("/api/todos")

    database.assert_called_once_with(DATABASE_URL)
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert todos.status_code == 200
    assert todos.json() == []
    database.return_value.dispose.assert_called_once_with()
