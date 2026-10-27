"""Fill gaps in the existing application's tests with the same agent, sandbox and checks as pull requests."""

import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from . import git, report


def _gap(path, stack, percent, uncovered):
    return {"path": path, "stack": stack, "coverage_percent": percent, "uncovered_lines": uncovered}


def backend_gaps(coverage_json: str) -> list[dict]:
    files = json.loads(coverage_json)["files"]
    gaps = [_gap(f"backend/{path}", "backend", round(item["summary"]["percent_covered"], 1), item["missing_lines"])
            for path, item in files.items() if item["missing_lines"]]
    return sorted(gaps, key=lambda g: (-len(g["uncovered_lines"]), g["path"]))


def _lcov(lcov_text: str):
    path, hits = None, {}
    for line in lcov_text.splitlines():
        if line.startswith("SF:"):
            path, hits[path] = line[3:], {}
        elif line.startswith("DA:") and path:
            number, count = line[3:].split(",")[:2]
            hits[path][int(number)] = int(count)
    return hits


def frontend_gaps(lcov_text: str) -> list[dict]:
    gaps = []
    for path, lines in _lcov(lcov_text).items():
        missing = sorted(n for n, count in lines.items() if count == 0)
        if missing:
            gaps.append(_gap(f"frontend/{path}", "frontend", round(100 * (len(lines) - len(missing)) / len(lines), 1), missing))
    return sorted(gaps, key=lambda g: (-len(g["uncovered_lines"]), g["path"]))


def backend_total(coverage_json: str) -> float:
    return round(json.loads(coverage_json)["totals"]["percent_covered"], 1)


def frontend_total(lcov_text: str) -> float:
    lines = [count for file in _lcov(lcov_text).values() for count in file.values()]
    return round(100 * sum(1 for c in lines if c) / len(lines), 1) if lines else 100.0


def select(gaps: list[dict], files: list[str] | None) -> list[dict]:
    return gaps if not files else [g for g in gaps if g["path"] in files]


def render_task(stack: str, gaps: list[dict]) -> str:
    return (
        "<task>\n"
        f"Mode: backfill. Stacks: {stack}.\n"
        "The listed files have uncovered behaviour. Add the missing unit tests, highest value first.\n"
        "Use the same workflow; treat each listed file as changed.\n"
        "</task>\n"
        "<coverage_gaps>\n" + "\n".join(json.dumps(g) for g in gaps) + "\n</coverage_gaps>\n"
    )


def make_context(stack: str, gaps: list[dict], head: str) -> dict:
    return {
        "mode": "backfill", "base": head, "head": head, "stacks": [stack], "should_run": True, "skip_reason": "",
        "files": [{"path": g["path"], "stack": stack, "kind": "source", "status": "M", "coverage_excluded": False}
                  for g in gaps],
    }


@contextmanager
def worktree(root: Path | str, where: Path | str, ref: str = "HEAD"):
    """A separate checkout of `ref` with the installed dependencies linked in, removed afterwards."""
    root, where = Path(root), Path(where)
    git.run(root, "worktree", "add", "--detach", str(where), ref)
    try:
        for relative in ("frontend/node_modules", "backend/.venv"):
            source = root / relative
            if source.exists():
                (where / relative).parent.mkdir(parents=True, exist_ok=True)
                (where / relative).symlink_to(source.resolve(), target_is_directory=True)
        yield where
    finally:
        git.run(root, "worktree", "remove", "--force", str(where), check=False)
        shutil.rmtree(where, ignore_errors=True)


def measure(root, report_path, base, stack="backend") -> dict:
    """Coverage of the whole stack after the proposal (there is no diff to measure in a backfill)."""
    report_path = Path(report_path)
    if stack == "backend":
        percent = backend_total((report_path.parent / "coverage.json").read_text())
    else:
        percent = frontend_total(report_path.read_text())
    return {"covered": 0, "total": 0, "percent": percent, "files": {}}


def report_markdown(stack: str, *, before: float, after: float, agent: dict, result: dict, verification: dict) -> str:
    t = report._text
    stack_result = (verification.get("stacks") or {}).get(stack, {})
    counts = stack_result.get("counts") or {}
    lines = [
        f"Tests added by the test agent for the existing {t(stack, 20)} code.",
        "",
        f"- Coverage of the {t(stack, 20)} code: {before}% before, {after}% after.",
        f"- Verified: {report._counts({'counts': counts}) if counts else 'no report'} "
        f"(three shuffled runs, all new tests passed).",
        f"- Run: {t(agent.get('model'), 60)}, {int(agent.get('turns') or 0)} turns, "
        f"{agent.get('duration_s')} s, skills {', '.join(t(s, 40) for s in agent.get('skills_used', [])) or 'none'}.",
        "",
        t(result.get("summary"), 800),
        "",
        "| File | Action | Reason | Tests |",
        "|---|---|---|---|",
    ]
    for d in result.get("decisions", []):
        tests = ", ".join(report._path(p) for p in d.get("test_files", [])) or "none"
        lines.append(f"| {report._path(d.get('file'))} | {t(d.get('action'), 10)} | {t(d.get('reason'), 300)} | {tests} |")
    findings = result.get("findings") or []
    if findings:
        lines += ["", "Findings:"]
        lines += [f"- **{t(f.get('kind'), 30)}** in {report._path(f.get('file'))}: {t(f.get('description'), 400)}" for f in findings]
    return "\n".join(lines) + "\n"
