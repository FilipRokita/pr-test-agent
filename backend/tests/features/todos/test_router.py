from datetime import date
from unittest.mock import patch

import pytest

from app.features.todos.schemas import TodoCreate, TodoStats, TodoUpdate

NOT_FOUND = {"detail": "Task not found."}


def test_list_returns_tasks_from_repository(client, repository_mock, todo):
    repository_mock.list.return_value = [todo]
    response = client.get("/api/todos")
    assert response.status_code == 200
    assert response.json() == [todo.model_dump(mode="json")]
    repository_mock.list.assert_called_once_with()


def test_stats_returns_repository_counts_for_today(client, repository_mock):
    today = date(2026, 10, 2)
    repository_mock.stats.return_value = TodoStats(total=5, completed=2, active=3, overdue=1)
    with patch("app.features.todos.router.date") as clock:
        clock.today.return_value = today
        response = client.get("/api/todos/stats")
    assert response.status_code == 200
    assert response.json() == {"total": 5, "completed": 2, "active": 3, "overdue": 1}
    repository_mock.stats.assert_called_once_with(today)
    repository_mock.get.assert_not_called()


def test_create_trims_input_and_returns_created_task(client, repository_mock, todo):
    repository_mock.create.return_value = todo
    response = client.post("/api/todos", json={"title": "  Plan the sprint  ", "priority": "high"})
    assert response.status_code == 201
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.create.assert_called_once_with(
        TodoCreate(title="Plan the sprint", priority="high")
    )


@pytest.mark.parametrize("payload", [
    {"title": "   "},
    {"title": "x" * 121},
    {"title": "Task", "priority": "urgent"},
    {"title": "Task", "due_date": "2026-02-30"},
])
def test_invalid_create_never_calls_repository(client, repository_mock, payload):
    assert client.post("/api/todos", json=payload).status_code == 422
    repository_mock.create.assert_not_called()


def test_get_returns_task(client, repository_mock, todo):
    repository_mock.get.return_value = todo
    response = client.get("/api/todos/7")
    assert response.status_code == 200
    assert response.json() == todo.model_dump(mode="json")
    repository_mock.get.assert_called_once_with(7)


def test_get_returns_404_for_missing_task(client, repository_mock):
    repository_mock.get.return_value = None
    response = client.get("/api/todos/404")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    repository_mock.get.assert_called_once_with(404)


def test_update_returns_updated_task(client, repository_mock, todo):
    updated = todo.model_copy(update={"completed": True})
    repository_mock.update.return_value = updated
    response = client.patch("/api/todos/7", json={"completed": True})
    assert response.status_code == 200
    assert response.json() == updated.model_dump(mode="json")
    repository_mock.update.assert_called_once_with(7, TodoUpdate(completed=True))


def test_update_returns_404_for_missing_task(client, repository_mock):
    repository_mock.update.return_value = None
    response = client.patch("/api/todos/404", json={"title": "New"})
    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    repository_mock.update.assert_called_once_with(404, TodoUpdate(title="New"))


def test_delete_returns_204_without_body(client, repository_mock):
    repository_mock.delete.return_value = True
    response = client.delete("/api/todos/7")
    assert response.status_code == 204
    assert response.content == b""
    repository_mock.delete.assert_called_once_with(7)


def test_delete_returns_404_for_missing_task(client, repository_mock):
    repository_mock.delete.return_value = False
    response = client.delete("/api/todos/404")
    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    repository_mock.delete.assert_called_once_with(404)


@pytest.mark.parametrize("method, kwargs", [
    ("get", {}),
    ("patch", {"json": {"title": "New"}}),
    ("delete", {}),
])
@pytest.mark.parametrize("todo_id", ["0", "-1", "abc"])
def test_invalid_task_id_never_calls_repository(client, repository_mock, method, kwargs, todo_id):
    response = client.request(method, f"/api/todos/{todo_id}", **kwargs)
    assert response.status_code == 422
    repository_mock.get.assert_not_called()
    repository_mock.update.assert_not_called()
    repository_mock.delete.assert_not_called()


@pytest.mark.parametrize("payload", [
    {},
    {"title": None},
    {"completed": "yes"},
    {"title": "Task", "owner": "me"},
])
def test_invalid_update_never_calls_repository(client, repository_mock, payload):
    assert client.patch("/api/todos/7", json=payload).status_code == 422
    repository_mock.update.assert_not_called()
