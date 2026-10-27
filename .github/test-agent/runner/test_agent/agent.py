"""Run the test-engineer agent with the Claude Agent SDK.

The model gets file tools restricted by hooks (see policy.py), the Skill tool for the plugin's skills, and one
custom tool that runs tests in the sandbox. It has no shell, no web access and no git.
"""

import tempfile
import time
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, HookMatcher, ResultMessage, SystemMessage, ToolUseBlock,
    create_sdk_mcp_server, query, tool,
)

from . import policy, sandbox, schema, tools

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugin"
SKILLS = ("analyze-changes", "write-backend-tests", "write-frontend-tests", "triage-failing-tests", "review-test-quality")
EXPECTED_TOOLS = {"Read", "Glob", "Grep", "Write", "Edit", "Skill", "StructuredOutput", "mcp__taskly__run_tests"}
AGENT_NAME = "test-agent:test-engineer"


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def write_hook(root: Path):
    async def hook(input_data, tool_use_id, context):
        path = input_data["tool_input"].get("file_path", "")
        if policy.can_write(root, path):
            return {}
        return _deny(f"Writing {path} is not allowed. Only test files may be created or edited.")
    return hook


def read_hook(root: Path):
    async def hook(input_data, tool_use_id, context):
        tool_input = input_data["tool_input"]
        if input_data["tool_name"] in ("Glob", "Grep") and not policy.glob_pattern_ok(tool_input.get("pattern", "")):
            return _deny(f"Pattern {tool_input.get('pattern')} leaves the repository.")
        path = tool_input.get("file_path") or tool_input.get("path") or str(root)
        if policy.can_read(root, path):
            return {}
        return _deny(f"Reading {path} is not allowed.")
    return hook


def audit_init(init: dict) -> list[str]:
    """Problems with the session the SDK started: unexpected tools, missing plugin, agent or skills."""
    problems = []
    for name in init.get("tools", []):
        if name not in EXPECTED_TOOLS:
            problems.append(f"unexpected tool available: {name}")
    if not any(p.get("name") == "test-agent" for p in init.get("plugins", [])):
        problems.append("plugin test-agent did not load")
    if AGENT_NAME not in init.get("agents", []):
        problems.append(f"agent {AGENT_NAME} is missing")
    for name in SKILLS:
        if f"test-agent:{name}" not in init.get("skills", []):
            problems.append(f"skill {name} is missing")
    return problems


def skills_used(calls: list[tuple[str, dict]]) -> list[str]:
    used = []
    for name, tool_input in calls:
        if name == "Skill":
            skill = tool_input.get("skill", "").removeprefix("test-agent:")
            if skill and skill not in used:
                used.append(skill)
    return used


def _tool_summary(result: dict) -> str:
    lines = [f"stack: {result['stack']}, ok: {result.get('ok')}"]
    if result.get("counts"):
        lines.append("counts: " + ", ".join(f"{k}={v}" for k, v in result["counts"].items()))
    if result.get("error"):
        lines.append(f"error: {result['error']}")
    if result.get("typecheck_ok") is False:
        lines.append("typecheck failed:\n" + result["typecheck_output"])
    for test in result.get("tests", []):
        if test["outcome"] in ("failed", "error"):
            lines.append(f"{test['outcome']}: {test['id']}: {test['message']}")
    lines.append("--- output tail ---\n" + result.get("output", ""))
    return "\n".join(lines)


def build_run_tests_tool(root: Path, work_dir: Path):
    counter = {"n": 0}

    @tool(
        "run_tests",
        "Run the backend or frontend tests in a sandbox without network or secrets. Input: stack ('backend' or "
        "'frontend'), paths (optional list of test files to run, default all), coverage (bool, adds a coverage "
        "report to the output).",
        {"type": "object",
         "properties": {"stack": {"type": "string", "enum": list(tools.STACKS)},
                        "paths": {"type": "array", "items": {"type": "string"}},
                        "coverage": {"type": "boolean"}},
         "required": ["stack"]},
    )
    async def run_tests(args):
        counter["n"] += 1
        try:
            out_dir = sandbox.prepare_out_dir(work_dir / f"run-{counter['n']}")
            result = tools.run_stack(root, args["stack"], args.get("paths") or [],
                                     coverage=bool(args.get("coverage")), out_dir=out_dir)
        except tools.ToolError as error:
            return {"content": [{"type": "text", "text": f"error: {error}"}], "isError": True}
        return {"content": [{"type": "text", "text": _tool_summary(result)}]}

    return run_tests


async def run_agent(root: Path, task: str, *, model: str, effort: str = "high", max_turns: int = 80,
                    max_budget_usd: float = 8.0) -> dict:
    root = Path(root).resolve()
    started = time.time()
    work = tempfile.mkdtemp(prefix="test-agent-")
    try:
        server = create_sdk_mcp_server("taskly", "1.0.0", [build_run_tests_tool(root, Path(work))])
        options = ClaudeAgentOptions(
            cwd=str(root),
            plugins=[{"type": "local", "path": str(PLUGIN_DIR)}],
            setting_sources=[],
            skills=[f"test-agent:{name}" for name in SKILLS],
            tools=["Read", "Glob", "Grep", "Write", "Edit", "Skill"],
            allowed_tools=["Read", "Glob", "Grep", "Skill", "Write", "Edit", "mcp__taskly__run_tests"],
            mcp_servers={"taskly": server},
            hooks={"PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[write_hook(root)]),
                                  HookMatcher(matcher="Read|Glob|Grep", hooks=[read_hook(root)])]},
            output_format={"type": "json_schema", "schema": schema.SCHEMA},
            model=model, effort=effort, max_turns=max_turns, max_budget_usd=max_budget_usd,
            env={"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "DISABLE_TELEMETRY": "1"},
        )
        init, calls, final = {}, [], None
        try:
            async for message in query(prompt=task, options=options):
                if isinstance(message, SystemMessage) and message.subtype == "init":
                    init = {key: message.data.get(key) for key in ("tools", "skills", "agents", "plugins", "model")}
                    init = {k: v or [] if k != "model" else v for k, v in init.items()}
                elif isinstance(message, AssistantMessage):
                    calls += [(b.name, b.input) for b in message.content if isinstance(b, ToolUseBlock)]
                elif isinstance(message, ResultMessage):
                    final = message
        except Exception as error:  # the SDK raises after yielding an error result
            if final is None:
                return _failure("agent_error", f"{type(error).__name__}: {error}", init, calls, started)
    finally:
        sandbox.remove_tree(work)

    if final is None:
        return _failure("agent_error", "the agent produced no result", init, calls, started)
    problems = audit_init(init)
    structured = final.structured_output
    status = "ok" if (final.subtype == "success" and structured is not None and not problems) else "agent_error"
    return {
        "status": status,
        "subtype": final.subtype,
        "problems": problems,
        "structured_output": structured,
        "skills_used": skills_used(calls),
        "tool_calls": len(calls),
        "denials": [d.get("tool_name") for d in (final.permission_denials or [])],
        "turns": final.num_turns,
        "duration_s": round(time.time() - started, 1),
        "cost_usd": final.total_cost_usd,
        "model": init.get("model") or model,
    }


def _failure(status, detail, init, calls, started) -> dict:
    return {"status": status, "subtype": detail, "problems": audit_init(init) if init else [],
            "structured_output": None, "skills_used": skills_used(calls), "tool_calls": len(calls),
            "denials": [], "turns": 0, "duration_s": round(time.time() - started, 1), "cost_usd": None,
            "model": init.get("model") if init else None}
