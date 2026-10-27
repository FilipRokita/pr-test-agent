"""The agent wiring end to end against a scripted fake model: no network, no secrets, no cost."""

import asyncio
import json

import pytest

from test_agent import agent
from tests.fake_api import FakeApi, call


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "backend/tests").mkdir(parents=True)
    (tmp_path / "backend/app").mkdir(parents=True)
    (tmp_path / "backend/app/x.py").write_text("def double(n):\n    return n * 2\n")
    return tmp_path


@pytest.fixture
def fake_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-for-tests")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    monkeypatch.setenv("DISABLE_TELEMETRY", "1")
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    return monkeypatch


FINAL = {"summary": "Added a test.", "findings": [], "decisions": [
    {"file": "backend/app/x.py", "action": "add", "reason": "double() had no test", "test_files": ["backend/tests/test_x.py"]}]}


def _run(repo, fake_env, script, task="Task text for the fake model."):
    with FakeApi(script) as api:
        fake_env.setenv("ANTHROPIC_BASE_URL", api.url)
        result = asyncio.run(agent.run_agent(repo, task, model="claude-opus-5-5", max_turns=15, max_budget_usd=1))
    return result, api


def test_a_scripted_session_loads_the_plugin_enforces_policy_and_returns_structured_output(repo, fake_env):
    script = [
        [call("t1", "Skill", {"skill": "test-agent:analyze-changes"})],
        [call("t2", "Write", {"file_path": str(repo / "backend/app/evil.py"), "content": "x = 1\n"})],
        [call("t3", "Read", {"file_path": "/etc/passwd"})],
        [call("t4", "Write", {"file_path": str(repo / "backend/tests/test_x.py"),
                              "content": "def test_double():\n    assert 2 * 2 == 4\n"})],
        [call("t5", "StructuredOutput", FINAL)],
    ]
    result, api = _run(repo, fake_env, script)

    assert result["status"] == "ok", result
    assert result["problems"] == []
    assert result["structured_output"] == FINAL
    assert result["skills_used"] == ["analyze-changes"]
    assert sorted(result["denials"]) == ["Read", "Write"]
    assert not (repo / "backend/app/evil.py").exists()
    assert (repo / "backend/tests/test_x.py").exists()

    first = json.dumps(api.requests[0])
    assert "test engineer for the Taskly repository" in first          # the plugin's agent prompt is in use
    assert "analyze-changes" in first                                  # our skills are listed
    assert "General Coding Principles" not in first                    # the developer's AGENTS.md is not
    assert "deep-research" not in first and "dataviz" not in first     # no bundled skills


def test_the_task_text_reaches_the_model(repo, fake_env):
    _, api = _run(repo, fake_env, [[call("t1", "StructuredOutput", FINAL)]], task="UNIQUE-TASK-MARKER-123")
    assert "UNIQUE-TASK-MARKER-123" in json.dumps(api.requests[0])


def test_a_model_that_never_answers_in_the_schema_is_an_agent_error(repo, fake_env):
    result, _ = _run(repo, fake_env, [])
    assert result["status"] == "agent_error"
    assert result["structured_output"] is None
