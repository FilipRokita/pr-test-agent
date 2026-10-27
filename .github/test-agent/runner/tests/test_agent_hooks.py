import asyncio

import pytest

from test_agent import agent


@pytest.fixture
def root(tmp_path):
    (tmp_path / "backend/tests").mkdir(parents=True)
    (tmp_path / "backend/app").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


def _call(hook, tool_name, tool_input):
    return asyncio.run(hook({"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}, "id", None))


def _denied(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def test_writes_to_test_files_are_allowed(root):
    hook = agent.write_hook(root)
    assert _call(hook, "Write", {"file_path": str(root / "backend/tests/test_new.py")}) == {}
    assert _call(hook, "Edit", {"file_path": "backend/tests/test_new.py"}) == {}


@pytest.mark.parametrize("path", ["backend/app/x.py", "backend/tests/conftest.py", ".github/workflows/ci.yml", "/etc/passwd"])
def test_writes_anywhere_else_are_denied_with_a_reason(root, path):
    result = _call(agent.write_hook(root), "Write", {"file_path": path})
    assert _denied(result)
    assert path in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_reads_inside_the_repository_are_allowed(root):
    hook = agent.read_hook(root)
    assert _call(hook, "Read", {"file_path": str(root / "backend/app/x.py")}) == {}
    assert _call(hook, "Grep", {"pattern": "def ", "path": str(root / "backend")}) == {}
    assert _call(hook, "Glob", {"pattern": "backend/tests/**/*.py"}) == {}


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": "/etc/passwd"}),
        ("Read", {"file_path": ".env"}),
        ("Read", {"file_path": ".git/config"}),
        ("Grep", {"pattern": "root", "path": "/etc"}),
        ("Glob", {"pattern": "/etc/*"}),
        ("Glob", {"pattern": "../../*"}),
        ("Glob", {"pattern": "*", "path": "/"}),
    ],
)
def test_reads_outside_the_allowed_area_are_denied(root, tool, tool_input):
    assert _denied(_call(agent.read_hook(root), tool, tool_input))


def test_a_search_without_a_path_searches_the_repository(root):
    assert _call(agent.read_hook(root), "Grep", {"pattern": "x"}) == {}


GOOD_INIT = {
    "tools": ["Edit", "Glob", "Grep", "Read", "Skill", "StructuredOutput", "Write", "mcp__taskly__run_tests"],
    "skills": [f"test-agent:{n}" for n in agent.SKILLS],
    "agents": ["claude", "Explore", "test-agent:test-engineer"],
    "plugins": [{"name": "test-agent"}],
}


def test_a_correct_session_has_no_problems():
    assert agent.audit_init(GOOD_INIT) == []


def test_an_extra_tool_is_a_problem():
    init = {**GOOD_INIT, "tools": [*GOOD_INIT["tools"], "Bash"]}
    assert any("Bash" in p for p in agent.audit_init(init))


def test_a_missing_plugin_or_skill_is_a_problem():
    assert agent.audit_init({**GOOD_INIT, "plugins": []})
    assert any("analyze-changes" in p for p in agent.audit_init({**GOOD_INIT, "skills": []}))
    assert any("test-engineer" in p for p in agent.audit_init({**GOOD_INIT, "agents": ["claude"]}))


def test_skills_used_come_from_skill_tool_calls_in_order_without_repeats():
    calls = [
        ("Skill", {"skill": "test-agent:analyze-changes"}),
        ("Read", {"file_path": "x"}),
        ("Skill", {"skill": "test-agent:write-backend-tests"}),
        ("Skill", {"skill": "test-agent:analyze-changes"}),
    ]
    assert agent.skills_used(calls) == ["analyze-changes", "write-backend-tests"]


def test_the_options_close_every_tool_source_except_the_plugin_and_run_tests(tmp_path):
    options = agent.build_options(tmp_path, tmp_path, model="m", effort="high", max_turns=5, max_budget_usd=1)
    assert options.strict_mcp_config is True                      # only the MCP servers we pass are used
    assert options.env["ENABLE_CLAUDEAI_MCP_SERVERS"] == "false"  # no account connectors such as mail or calendar
    assert options.setting_sources == []
    assert sorted(options.tools) == ["Edit", "Glob", "Grep", "Read", "Skill", "Write"]
    assert set(options.mcp_servers) == {"taskly"}


def test_a_session_with_unexpected_tools_is_stopped_before_the_model_acts(tmp_path, monkeypatch):
    from claude_agent_sdk import AssistantMessage, SystemMessage, TextBlock

    consumed = []

    async def fake_query(prompt, options):
        yield SystemMessage(subtype="init", data={**{"tools": [*GOOD_INIT["tools"], "mcp__connector__send_mail"],
                                                      "skills": GOOD_INIT["skills"], "agents": GOOD_INIT["agents"],
                                                      "plugins": GOOD_INIT["plugins"], "model": "m"}})
        consumed.append("after init")
        yield AssistantMessage(content=[TextBlock(text="acting")], model="m")

    monkeypatch.setattr(agent, "query", fake_query)
    result = asyncio.run(agent.run_agent(tmp_path, "task", model="m"))
    assert result["status"] == "agent_error"
    assert any("mcp__connector__send_mail" in p for p in result["problems"])
    assert consumed == []
