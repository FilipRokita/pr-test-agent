# Backend test examples

Every example runs in this repository. Copy the shape, not the names.

## Router: 404 and rejected input (uses `client` and `repository_mock`)

```python
def test_get_returns_404_for_a_missing_task(client, repository_mock):
    repository_mock.get.return_value = None
    response = client.get("/api/todos/404")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found."}
    repository_mock.get.assert_called_once_with(404)


def test_a_path_id_of_zero_is_rejected_before_the_repository(client, repository_mock):
    assert client.get("/api/todos/0").status_code == 422
    repository_mock.get.assert_not_called()
```

Why: the status, the exact body and the collaborator call are all asserted; a rejected request proves the
repository was never reached.

## Router: many invalid inputs, one test (from `test_router.py`)

```python
@pytest.mark.parametrize("payload", [
    {"title": "   "},
    {"title": "x" * 121},
    {"title": "Task", "priority": "urgent"},
])
def test_invalid_create_never_calls_repository(client, repository_mock, payload):
    assert client.post("/api/todos", json=payload).status_code == 422
    repository_mock.create.assert_not_called()
```

## Repository: `create` needs an id after `refresh`

`create()` maps the record after `session.refresh(record)`, so a plain `Mock(spec=Session)` leaves `id` unset.

```python
def test_create_assigns_an_id_after_refresh():
    session = Mock(spec=Session)

    def refresh(record):
        record.id = 7

    session.refresh.side_effect = refresh
    todo = TodoRepository(session).create(TodoCreate(title="Plan"))
    assert todo.id == 7 and todo.title == "Plan"
    session.add.assert_called_once()
    session.commit.assert_called_once_with()
```

## Repository: check the query, not only the result (from `test_repository.py`)

```python
statement = session.scalars.call_args.args[0]
expected = select(TodoRecord).order_by(TodoRecord.created_at.desc(), TodoRecord.id.desc())
assert statement.compare(expected)
assert "ORDER BY todos.created_at DESC, todos.id DESC" in str(statement.compile(dialect=postgresql.dialect()))
```

## Health: the repository mock has no `session`, so build the dependency yourself

```python
def test_health_checks_the_database_through_the_repository():
    session = Mock()
    repository = Mock(session=session)
    app = FastAPI()
    app.include_router(health_router)
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    session.execute.assert_called_once()
```

## Lifespan: patch where the names are used, check cleanup on failure

```python
def test_the_lifespan_creates_the_session_factory_and_disposes_the_engine():
    app = FastAPI(lifespan=lifespan)
    app.state.database_url = "postgresql+psycopg://u:p@localhost:5432/db"
    engine = Mock()
    with (
        patch("app.core.lifespan.create_database_engine", return_value=engine) as create_engine,
        patch("app.core.lifespan.initialize") as initialize,
        patch("app.core.lifespan.create_session_factory", return_value="factory"),
    ):
        with TestClient(app):
            assert app.state.session_factory == "factory"
            initialize.assert_called_once_with(engine)
    create_engine.assert_called_once_with("postgresql+psycopg://u:p@localhost:5432/db")
    engine.dispose.assert_called_once_with()
```

For the failure case, give `initialize` a `side_effect=RuntimeError(...)`, enter the client inside
`pytest.raises`, and assert `engine.dispose` was still called.

## Dependencies: drive the generator by hand (from `test_dependencies.py`)

```python
dependency = get_repository(request)
with pytest.raises(RuntimeError, match="Session unavailable"):
    next(dependency)
```
