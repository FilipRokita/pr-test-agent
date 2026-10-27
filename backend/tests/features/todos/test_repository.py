from datetime import date, datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.features.todos.models import TodoRecord
from app.features.todos.repository import TodoRepository
from app.features.todos.schemas import TodoCreate, TodoStats, TodoUpdate

NOW = datetime(2026, 10, 2, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def frozen_now():
    with patch("app.features.todos.repository.datetime") as clock:
        clock.now.return_value = NOW
        yield clock


def test_list_maps_models_and_orders_tasks_newest_first(model_factory, todo_values, todo):
    session = Mock(spec=Session)
    session.scalars.return_value = [model_factory(todo_values)]
    assert TodoRepository(session).list() == [todo]
    statement = session.scalars.call_args.args[0]
    expected = select(TodoRecord).order_by(TodoRecord.created_at.desc(), TodoRecord.id.desc())
    assert statement.compare(expected)
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY todos.created_at DESC, todos.id DESC" in compiled


def test_get_returns_none_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None
    assert TodoRepository(session).get(404) is None
    session.get.assert_called_once_with(TodoRecord, 404)


def test_create_persists_record_with_utc_timestamps_and_returns_task(frozen_now):
    session = Mock(spec=Session)
    session.refresh.side_effect = lambda record: setattr(record, "id", 7)
    payload = TodoCreate(title="Plan the sprint", description="First", priority="high")

    created = TodoRepository(session).create(payload)

    record = session.add.call_args.args[0]
    assert isinstance(record, TodoRecord)
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(record)
    frozen_now.now.assert_called_once_with(timezone.utc)
    assert created.model_dump() == {
        "id": 7,
        "title": "Plan the sprint",
        "description": "First",
        "priority": "high",
        "due_date": None,
        "completed": False,
        "created_at": NOW,
        "updated_at": NOW,
    }


def test_update_changes_only_sent_fields_and_refreshes_updated_at(
    frozen_now, model_factory, todo_values
):
    record = model_factory({**todo_values, "due_date": date(2026, 11, 1)})
    session = Mock(spec=Session)
    session.get.return_value = record

    updated = TodoRepository(session).update(7, TodoUpdate(completed=True, due_date=None))

    session.get.assert_called_once_with(TodoRecord, 7)
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(record)
    assert updated.model_dump() == {
        **todo_values,
        "completed": True,
        "due_date": None,
        "updated_at": NOW,
    }


def test_update_returns_none_and_skips_commit_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None

    assert TodoRepository(session).update(404, TodoUpdate(title="New")) is None

    session.get.assert_called_once_with(TodoRecord, 404)
    session.commit.assert_not_called()


def test_delete_removes_existing_task(model_factory, todo_values):
    record = model_factory(todo_values)
    session = Mock(spec=Session)
    session.get.return_value = record

    assert TodoRepository(session).delete(7) is True

    session.get.assert_called_once_with(TodoRecord, 7)
    session.delete.assert_called_once_with(record)
    session.commit.assert_called_once_with()


def test_delete_returns_false_and_skips_commit_for_missing_task():
    session = Mock(spec=Session)
    session.get.return_value = None

    assert TodoRepository(session).delete(404) is False

    session.delete.assert_not_called()
    session.commit.assert_not_called()


def test_stats_counts_only_active_tasks_due_before_today_as_overdue(model_factory, todo_values):
    today = date(2026, 10, 2)
    yesterday = date(2026, 10, 1)
    tasks = [
        {"completed": False, "due_date": yesterday},  # overdue
        {"completed": False, "due_date": today},  # due today: not overdue
        {"completed": False, "due_date": None},  # no due date: not overdue
        {"completed": True, "due_date": yesterday},  # completed: never overdue
        {"completed": True, "due_date": None},
    ]
    session = Mock(spec=Session)
    session.scalars.return_value = [
        model_factory({**todo_values, "id": index, **task}) for index, task in enumerate(tasks, 1)
    ]

    stats = TodoRepository(session).stats(today)

    assert stats == TodoStats(total=5, completed=2, active=3, overdue=1)


def test_stats_returns_zeros_without_tasks():
    session = Mock(spec=Session)
    session.scalars.return_value = []

    stats = TodoRepository(session).stats(date(2026, 10, 2))

    assert stats == TodoStats(total=0, completed=0, active=0, overdue=0)
