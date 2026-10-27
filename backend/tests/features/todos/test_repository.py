from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.features.todos.models import TodoRecord
from app.features.todos.repository import TodoRepository


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


@pytest.mark.parametrize(
    ("completed_flags", "expected"),
    [
        ([], 0),
        ([False, False], 0),
        ([True, False, True], 2),
    ],
)
def test_count_completed_counts_only_completed_tasks(model_factory, todo_values, completed_flags, expected):
    session = Mock(spec=Session)
    session.scalars.return_value = [
        model_factory({**todo_values, "id": index + 1, "completed": completed})
        for index, completed in enumerate(completed_flags)
    ]
    assert TodoRepository(session).count_completed() == expected
    session.scalars.assert_called_once()
