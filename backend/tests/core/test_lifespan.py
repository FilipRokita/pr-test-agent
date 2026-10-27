from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.lifespan import lifespan

DATABASE_URL = "postgresql+psycopg://taskly:taskly@localhost:5432/taskly"


@pytest.fixture
def database():
    with (
        patch("app.core.lifespan.create_database_engine") as create_engine,
        patch("app.core.lifespan.initialize") as initialize,
        patch("app.core.lifespan.create_session_factory") as create_session_factory,
    ):
        yield create_engine, initialize, create_session_factory


@pytest.fixture
def app():
    app = FastAPI(lifespan=lifespan)
    app.state.database_url = DATABASE_URL
    return app


def test_lifespan_initializes_database_and_disposes_engine_on_shutdown(app, database):
    create_engine, initialize, create_session_factory = database
    engine = create_engine.return_value

    with TestClient(app):
        create_engine.assert_called_once_with(DATABASE_URL)
        initialize.assert_called_once_with(engine)
        create_session_factory.assert_called_once_with(engine)
        assert app.state.session_factory is create_session_factory.return_value
        engine.dispose.assert_not_called()

    engine.dispose.assert_called_once_with()


def test_lifespan_disposes_engine_when_initialization_fails(app, database):
    create_engine, initialize, create_session_factory = database
    initialize.side_effect = RuntimeError("Database unavailable")

    with pytest.raises(RuntimeError, match="Database unavailable"):
        with TestClient(app):
            pass

    create_session_factory.assert_not_called()
    create_engine.return_value.dispose.assert_called_once_with()
