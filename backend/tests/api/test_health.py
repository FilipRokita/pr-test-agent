from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_repository
from app.api.health import router
from app.features.todos.models import TodoRecord


@pytest.fixture
def health_repository():
    return Mock(session=Mock(spec=Session))


@pytest.fixture
def health_client(health_repository):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repository] = lambda: health_repository
    with TestClient(app) as client:
        yield client


def test_health_probes_database_and_reports_ok(health_client, health_repository):
    response = health_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    statement = health_repository.session.execute.call_args.args[0]
    assert statement.compare(select(TodoRecord.id).limit(1))


def test_health_propagates_database_failure(health_client, health_repository):
    health_repository.session.execute.side_effect = RuntimeError("Database unavailable")
    with pytest.raises(RuntimeError, match="Database unavailable"):
        health_client.get("/api/health")
