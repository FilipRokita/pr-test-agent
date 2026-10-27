from unittest.mock import patch

import pytest

from app.core.config import resolve_database_url

POSTGRES_ENV = {
    "POSTGRES_USER": "taskly",
    "POSTGRES_PASSWORD": "s3cret",
    "POSTGRES_HOST": "db",
    "DB_PORT": "5433",
    "POSTGRES_DB": "tasks",
}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    with patch("app.core.config.load_dotenv") as load_dotenv:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        for name in POSTGRES_ENV:
            monkeypatch.delenv(name, raising=False)
        yield load_dotenv


def test_explicit_url_wins_over_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env/db")
    assert resolve_database_url("postgresql+psycopg://explicit/db") == "postgresql+psycopg://explicit/db"


def test_database_url_environment_variable_is_used_when_no_explicit_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://env/db")
    for name, value in POSTGRES_ENV.items():
        monkeypatch.setenv(name, value)
    assert resolve_database_url() == "postgresql+psycopg://env/db"


def test_url_is_built_from_postgres_variables_without_hiding_password(monkeypatch):
    for name, value in POSTGRES_ENV.items():
        monkeypatch.setenv(name, value)
    assert resolve_database_url() == "postgresql+psycopg://taskly:s3cret@db:5433/tasks"


def test_missing_postgres_variable_raises_key_error(monkeypatch):
    for name, value in POSTGRES_ENV.items():
        if name != "POSTGRES_HOST":
            monkeypatch.setenv(name, value)
    with pytest.raises(KeyError, match="POSTGRES_HOST"):
        resolve_database_url()


def test_dotenv_is_loaded_without_overriding_existing_variables(isolated_env):
    resolve_database_url("postgresql+psycopg://explicit/db")
    path = isolated_env.call_args.args[0]
    assert path.name == ".env"
    assert isolated_env.call_args.kwargs == {"override": False}
