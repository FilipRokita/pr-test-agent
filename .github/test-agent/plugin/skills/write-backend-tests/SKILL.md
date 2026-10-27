---
name: write-backend-tests
description: Conventions and patterns for pytest unit tests of the Taskly FastAPI backend (routers, repository, dependencies, config, app factory, lifespan). Use before writing or editing any file under backend/tests.
---

# Backend unit tests (pytest)

## Ground rules

- Unit tests only. No database, no network, no real `.env`. Never create an engine that connects.
- Mirror the source path: `backend/app/features/todos/router.py` -> `backend/tests/features/todos/test_router.py`.
  Create missing empty `__init__.py` files in new test folders.
- Never import `app.main` (it reads environment variables that the sandbox does not have).
- Plain test functions, names that state the behaviour: `test_update_returns_404_for_missing_task`.
- Prefer `pytest.mark.parametrize` for input variations.
- Assert the full response body (`response.json() == ...`) and the exact collaborator call
  (`assert_called_once_with(...)`).

## Fixtures you must reuse (`backend/tests/conftest.py`, `backend/tests/mocks.py`)

| Fixture | What it gives |
|---|---|
| `repository_mock` | `create_autospec(TodoRepository, instance=True)`, `list` returns `[]` |
| `client` | `TestClient` for a bare FastAPI app with only the todos router and `get_repository` overridden by `repository_mock` |
| `todo_values` | dict of a valid todo (id 7, timezone-aware timestamps) |
| `todo` | `Todo` built from `todo_values` |
| `model_factory` | builds a `TodoRecord` from a dict |

`conftest.py` and `mocks.py` are read-only. When a test needs another fixture, define it in that test file.

## Patterns per layer

- **Router**: call through `client`, set `repository_mock.<method>.return_value`, assert status, body, and
  the repository call. Not-found paths return 404 with `{"detail": "Task not found."}`. Invalid input
  returns 422 and the repository is never called.
- **Repository**: `Mock(spec=Session)`; assert `session.add/commit/refresh/delete/get` calls and returned
  `Todo`. `create()` maps the record after `refresh`, so give the record an id there:
  `session.refresh.side_effect = lambda record: setattr(record, "id", 7)`. For queries, compare the
  statement with `statement.compare(expected)` and check the compiled SQL with the PostgreSQL dialect, as
  `test_list_maps_models_and_orders_tasks_newest_first` does. Freeze "now" by patching
  `app.features.todos.repository.datetime` when timestamps matter.
- **Dependencies**: drive the generator by hand (`next(dependency)`, then `dependency.throw(...)` or
  `dependency.close()`) and assert `rollback` and `close` on a mock session.
- **Config**: `monkeypatch.setenv`/`delenv` for every variable you rely on, and patch
  `app.core.config.load_dotenv` so the repository's `.env` never leaks into the test.
- **Health**: `repository_mock` has no `session` attribute (autospec drops instance attributes). Build an
  app with the health router and override `get_repository` with a mock that has `session = Mock()`, or
  go through the lifespan with a patched session factory.
- **Factory, lifespan**: patch `create_database_engine`, `initialize`, `create_session_factory` where they
  are imported (`app.core.lifespan.<name>`), pass an explicit `database_url` to `create_app`, use
  `TestClient` as a context manager to run the lifespan, and assert `engine.dispose()` runs even when
  startup fails.


## Run

`run_tests` with `stack: "backend"`, `paths` set to the files you touched; `coverage: true` for the
final check.
