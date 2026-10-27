"""Render the pull request comment. Every number comes from the verification step, never from the model.

Text written by the model is untrusted: it is escaped so it cannot add markup, mentions, references, a second
marker or break out of a table cell.
"""

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
            return "No new tests needed"
        return f"{added} added, {updated} updated, all verified"
    if verification.get("status") == "rejected":
        return "Proposed tests were rejected by the checks"
    return "Proposed tests did not pass verification"


def render(ctx: dict, agent: dict | None, verification: dict | None, run_url: str = "") -> str:
    lines = [MARKER, f"## Test agent: {_headline(ctx, agent, verification)}", ""]
    output = (agent or {}).get("structured_output") or {}

    if output.get("summary"):
        lines += [_text(output["summary"], 600), ""]

    if verification and verification.get("stacks"):
        lines += ["| Stack | Tests after the proposal |", "|---|---|"]
        for name, stack in verification["stacks"].items():
            lines.append(f"| {_text(name, 20)} | {_counts(stack)} |")
        lines.append("")
        if verification.get("patch_files"):
            lines += ["Files in the proposal: " + ", ".join(_path(p) for p in verification["patch_files"]), ""]

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
    return "\n".join(lines).rstrip() + "\n"
