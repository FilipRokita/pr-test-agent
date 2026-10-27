"""Render the pull request comment. Every number comes from the verification step, never from the model.

Text written by the model is untrusted: it is escaped so it cannot add markup, mentions, references, a second
marker or break out of a table cell.
"""

import json
import re

MARKER = "<!-- taskly-test-agent -->"
_ZERO_WIDTH = "​"


def _text(value, limit=300) -> str:
    """One line of safe, escaped text."""
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(value) > limit:
        value = value[: limit - 1] + "…"
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value = re.sub(r"([\\`*_\[\]()|~!])", r"\\\1", value)
    # A zero-width character breaks mentions (@name) and references (#123) without changing how text reads.
    value = value.replace("@", "@" + _ZERO_WIDTH).replace("#", "#" + _ZERO_WIDTH)
    return value


def _path(value) -> str:
    return "`" + re.sub(r"[`\s|<>]", "", str(value or ""))[:200] + "`"


def _counts(stack: dict) -> str:
    counts = stack.get("counts")
    if not counts:
        return "no report"
    parts = [f"{counts['passed']} passed"]
    for key in ("failed", "error", "skipped"):
        if counts.get(key):
            parts.append(f"{counts[key]} {key}")
    return ", ".join(parts)


def _runs(stack: dict) -> str:
    if stack.get("error"):
        return f"error: {_text(stack['error'], 120)}"
    runs = stack.get("runs") or []
    if runs and all(r == runs[0] for r in runs):
        return _counts({"counts": runs[0]}) + " in each run"
    return _counts(stack)


def _coverage(stack: dict) -> str:
    cov = stack.get("coverage")
    if cov is None:
        return "not available"
    if cov.get("percent") is None:
        return "no executable lines changed"
    return f"{cov['percent']}% ({cov['covered']}/{cov['total']})"


def _revert(stack: dict) -> str:
    revert = stack.get("revert") or {}
    if not revert.get("checked"):
        return "not checked: " + _text(revert.get("reason", "no information"), 120)
    return f"{revert['detect']} of {revert['total']}"


def _ids(items) -> str:
    return ", ".join(f"`{re.sub(r'\s+', ' ', re.sub(r'[`|<>@#]', '', i)).strip()[:120]}`" for i in items[:10]) + (" and more" if len(items) > 10 else "")


def _problems(verification: dict) -> list[str]:
    lines = []
    for name, stack in verification["stacks"].items():
        label = _text(name, 20)
        if stack.get("breaks_existing"):
            lines += [f"**This pull request breaks {len(stack['breaks_existing'])} existing {label} tests** "
                      f"(they already fail without the proposed tests): {_ids(stack['breaks_existing'])}", ""]
        for key, text in (("failing", "Proposed tests that failed"), ("flaky", "Tests that changed outcome between runs"),
                          ("broken_by_patch", "Existing tests broken by the proposal")):
            if stack.get(key):
                lines += [f"**{text} ({label}):** {_ids(stack[key])}", ""]
        if stack.get("removed"):
            lines += [f"**Tests removed or renamed in the proposal ({label}):** {_ids(stack['removed'])}", ""]
        if stack.get("ids_changed"):
            lines += [f"**The set of existing {label} tests changed**, which a proposal must not do.", ""]
        weak = (stack.get("revert") or {}).get("weak") or []
        if weak:
            lines += [f"**Weak tests ({label}):** these pass even with the old source, so they do not detect "
                      f"the change: {_ids(weak)}", ""]
    for warning in verification.get("warnings") or []:
        lines += [f"Note: {_text(warning, 200)}", ""]
    return lines


def _headline(ctx, agent, verification) -> str:
    if not ctx.get("should_run"):
        return f"Skipped: {_text(ctx.get('skip_reason'), 200)}"
    if agent and agent.get("status") == "skipped_no_credentials":
        return "Skipped: no LLM credentials are configured for this repository"
    if agent is None or agent.get("status") != "ok":
        detail = _text((agent or {}).get("subtype") or "no result", 120)
        return f"Agent run failed: {detail}"
    if verification is None:
        return "Verification did not run"
    decisions = (agent.get("structured_output") or {}).get("decisions", [])
    added = sum(1 for d in decisions if d.get("action") == "add")
    updated = sum(1 for d in decisions if d.get("action") == "update")
    if verification.get("status") == "verified":
        if not verification.get("patch_files"):
            broken = sum(len(s.get("breaks_existing") or []) for s in (verification.get("stacks") or {}).values())
            return f"This pull request breaks {broken} existing tests" if broken else "No new tests needed"
        return f"{added} added, {updated} updated, all verified"
    if verification.get("status") == "error":
        return "Verification could not run: " + _text(verification.get("reason"), 200)
    if verification.get("status") == "rejected":
        reason = _text(verification.get("reason"), 300)
        return "Proposed tests were rejected by the checks" + (f": {reason}" if reason else "")
    return "Proposed tests did not pass verification"


STATE_PREFIX = "<!-- taskly-test-agent-state "


def previous_head(comment_body: str) -> str | None:
    """The head commit that the last completed run analysed, read back from the comment."""
    match = re.search(r"<!-- taskly-test-agent-state (\{.*?\}) -->", comment_body)
    if not match:
        return None
    try:
        head = json.loads(match.group(1)).get("head", "")
    except ValueError:
        return None
    return head if re.fullmatch(r"[0-9a-f]{40}", head or "") else None


def render_pull_request_body(ctx: dict, agent: dict, verification: dict) -> str:
    output = agent.get("structured_output") or {}
    files = ", ".join(_path(p) for p in verification.get("patch_files", []))
    return "\n".join([
        f"Tests proposed by the test agent for #{int(ctx['pull_request'])}. They are verified: see the comment on that "
        "pull request for the decisions, the three shuffled runs and the coverage of the changed lines.",
        "",
        _text(output.get("summary"), 600),
        "",
        f"Files: {files}",
        "",
        "CI on this pull request starts after one approval click, because GitHub holds runs started by the "
        "workflow token. Merge it into the branch of the original pull request if the tests are wanted.",
    ])


def render(ctx: dict, agent: dict | None, verification: dict | None, run_url: str = "", stacked: int | None = None,
           note: str = "") -> str:
    lines = [MARKER, f"## Test agent: {_headline(ctx, agent, verification)}", ""]
    if stacked:
        lines += [f"Tests are proposed in #{int(stacked)}, stacked on this branch. CI on that pull request starts "
                  "after one approval click. CI on this pull request remains the merge gate.", ""]
    if note:
        lines += [_text(note, 300), ""]
    output = (agent or {}).get("structured_output") or {}

    if output.get("summary"):
        lines += [_text(output["summary"], 600), ""]

    if verification and verification.get("stacks"):
        lines += ["| Stack | Tests (3 shuffled runs) | Changed-line coverage | New tests that detect the change |",
                  "|---|---|---|---|"]
        for name, stack in verification["stacks"].items():
            lines.append(f"| {_text(name, 20)} | {_runs(stack)} | {_coverage(stack)} | {_revert(stack)} |")
        lines.append("")
        if verification.get("patch_files"):
            lines += ["Files in the proposal: " + ", ".join(_path(p) for p in verification["patch_files"]), ""]
        lines += _problems(verification)

    findings = output.get("findings") or []
    if findings:
        lines.append("### Findings")
        for finding in findings:
            where = _path(finding.get("file")) + (f":{int(finding['line'])}" if finding.get("line") else "")
            lines.append(f"- **{_text(finding.get('kind'), 30)}** in {where}: {_text(finding.get('description'), 600)}")
        lines.append("")

    decisions = output.get("decisions") or []
    if decisions:
        lines += ["<details><summary>Decisions per file</summary>", "",
                  "| File | Action | Reason | Tests |", "|---|---|---|---|"]
        for d in decisions:
            tests = ", ".join(_path(t) for t in d.get("test_files", [])) or "none"
            lines.append(f"| {_path(d.get('file'))} | {_text(d.get('action'), 10)} | {_text(d.get('reason'), 300)} | {tests} |")
        lines += ["", "</details>", ""]

    if agent:
        details = [
            f"model: {_text(agent.get('model'), 60)}",
            f"turns: {int(agent.get('turns') or 0)}",
            f"duration: {agent.get('duration_s')} s",
            f"cost: {agent.get('cost_usd')} USD (nominal)",
            "skills invoked: " + (", ".join(_text(s, 40) for s in agent.get("skills_used", [])) or "none"),
        ]
        if run_url:
            details.append(f"[workflow run]({run_url})")
        lines += ["<details><summary>Run</summary>", "", *[f"- {d}" for d in details], "", "</details>"]
    if agent and agent.get("status") == "ok" and verification is not None and re.fullmatch(r"[0-9a-f]{40}", ctx.get("head") or ""):
        lines += ["", f'{STATE_PREFIX}{json.dumps({"head": ctx["head"]})} -->']
    return "\n".join(lines).rstrip() + "\n"
