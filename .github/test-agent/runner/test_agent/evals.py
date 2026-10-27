"""Evaluation scenarios: fixed pull requests with deterministic expectations about what the agent must do.

A scenario is a directory with `scenario.json` (title, body, expectations) and `change.patch` (the change of the
pull request). `check` compares the outcome of a run with the expectations; `execute` runs one scenario.

Expectations (all optional except `runs`):
  runs                          false when the pull request must be skipped without running the agent
  verification                  required status of the verification, for example "verified"
  decisions                     {source file: [allowed actions]}
  min_changed_line_coverage     {stack: percent}
  findings_required/forbidden   kinds of findings
  patch_only_under              every file of the proposal starts with one of these prefixes
  patch_must_touch              files the proposal must change
  patch_must_not_remove_lines_in files whose existing lines the proposal must leave alone
  patch_forbidden_substrings    text that must not appear in the proposal
  breaks_existing_at_least      {stack: n} existing tests the pull request itself must be shown to break
"""

import asyncio
import json
import re
from pathlib import Path

from . import agent, backfill, context, git, patch, schema, verify


def _removed_lines(patch_text: str, path: str) -> list[str]:
    removed, current = [], None
    for line in patch_text.splitlines():
        header = re.match(r"^diff --git a/(.+) b/(.+)$", line)
        if header:
            current = header.group(2)
        elif current == path and line.startswith("-") and not line.startswith("---"):
            removed.append(line)
    return removed


def check(expect: dict, outcome: dict) -> list[str]:
    """Return what differs from the expectations; an empty list means the scenario passed."""
    ctx = outcome["ctx"]
    if not expect.get("runs", True):
        return ["the agent should not have run for this pull request"] if ctx["should_run"] else []
    if not ctx["should_run"]:
        return [f"the agent should have run but the pull request was skipped: {ctx.get('skip_reason')}"]

    result = outcome.get("agent")
    if not result or result.get("status") != "ok":
        return [f"the agent run failed: {(result or {}).get('subtype')}"]

    failures = []
    output = result["structured_output"]
    verification = outcome["verification"]
    patch_text = outcome.get("patch") or ""
    files = patch.changed_paths(patch_text)

    if "verification" in expect and verification["status"] != expect["verification"]:
        failures.append(f"verification was {verification['status']}, expected {expect['verification']}"
                        + (f" ({verification.get('reason')})" if verification.get("reason") else ""))

    actions = {d["file"]: d["action"] for d in output["decisions"]}
    for path, allowed in expect.get("decisions", {}).items():
        if actions.get(path) not in allowed:
            failures.append(f"decision for {path} was {actions.get(path)}, expected one of {allowed}")

    for stack, minimum in expect.get("min_changed_line_coverage", {}).items():
        coverage = ((verification.get("stacks") or {}).get(stack) or {}).get("coverage")
        percent = (coverage or {}).get("percent")
        if percent is None or percent < minimum:
            failures.append(f"changed-line coverage of {stack} was {percent}, expected at least {minimum}")

    kinds = {f["kind"] for f in output["findings"]}
    for kind in expect.get("findings_required", []):
        if kind not in kinds:
            failures.append(f"the finding {kind} was expected but not reported")
    for kind in expect.get("findings_forbidden", []):
        if kind in kinds:
            failures.append(f"the finding {kind} must not be reported")

    prefixes = tuple(expect.get("patch_only_under", []))
    if prefixes:
        failures += [f"the proposal touches {path}, outside {list(prefixes)}" for path in files if not path.startswith(prefixes)]
    failures += [f"the proposal must change {path}" for path in expect.get("patch_must_touch", []) if path not in files]
    failures += [f"the proposal removes existing lines in {path}" for path in expect.get("patch_must_not_remove_lines_in", [])
                 if _removed_lines(patch_text, path)]
    failures += [f"the proposal contains {text!r}" for text in expect.get("patch_forbidden_substrings", []) if text in patch_text]

    for stack, minimum in expect.get("breaks_existing_at_least", {}).items():
        broken = ((verification.get("stacks") or {}).get(stack) or {}).get("breaks_existing") or []
        if len(broken) < minimum:
            failures.append(f"expected the pull request to be shown breaking at least {minimum} existing {stack} tests, got {len(broken)}")
    return failures


def summary(rows: list[dict]) -> str:
    lines = ["| Scenario | Passed | Cost (nominal USD) | Turns | Failing assertions |", "|---|---|---|---|---|"]
    for row in rows:
        results = row["results"]
        passed = sum(1 for failures in results if not failures)
        reasons = sorted({failure for failures in results for failure in failures})
        lines.append(f"| {row['name']} | {passed} of {len(results)} | {row['cost']:.2f} | {row['turns']} | "
                     f"{'; '.join(reasons).replace('|', '/') or 'none'} |")
    return "\n".join(lines) + "\n"


def load(scenario_dir: Path) -> dict:
    scenario = json.loads((scenario_dir / "scenario.json").read_text())
    scenario["patch"] = (scenario_dir / "change.patch").read_text()
    return scenario


def execute(root: Path, scenario: dict, *, work: Path, model: str, max_turns: int, budget: float) -> dict:
    """Run one scenario: apply its change on a copy of HEAD, run the agent, verify in a fresh copy."""
    base = git.run(root, "rev-parse", "HEAD").strip()
    with backfill.worktree(root, work / "agent-tree") as tree:
        git.run(tree, "apply", "--whitespace=nowarn", "-", stdin=scenario["patch"])
        git.run(tree, "add", "-A", "--", ".", ":(exclude)backend/.venv", ":(exclude)frontend/node_modules")
        git.run(tree, "commit", "-q", "-m", scenario["title"],
                config=(("user.name", "scenario"), ("user.email", "scenario@example.invalid")))
        head = git.run(tree, "rev-parse", "HEAD").strip()
        ctx = context.from_git(tree, base=base, head=head, title=scenario["title"], body=scenario["body"])
        outcome = {"ctx": ctx, "agent": None, "patch": "", "verification": None}
        if not ctx["should_run"]:
            return outcome
        result = asyncio.run(agent.run_agent(tree, context.render_task(ctx), model=model,
                                             max_turns=max_turns, max_budget_usd=budget))
        if result["structured_output"] is not None:
            sources = [f["path"] for f in ctx["files"] if f["kind"] == "source" and f["status"] != "D"]
            result["structured_output"] = schema.normalise(result["structured_output"], sources)
        outcome.update(agent=result, patch=patch.create(tree))
    if result["status"] != "ok":
        return outcome
    with backfill.worktree(root, work / "verify-tree", ref=head) as tree:
        outcome["verification"] = verify.verify(tree, ctx, outcome["patch"], out_root=work / "verify-out")
    return outcome
