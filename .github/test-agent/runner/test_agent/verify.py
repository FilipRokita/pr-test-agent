"""Check a proposed patch before it is published.

This runs in a job that holds no secrets. The patch is data: it is checked by the guard first, then applied to a
clean checkout, scanned for secrets, and the tests are run in the sandbox: once without the patch (baseline) and
three times, in random order, with it. Everything reported comes from these runs, never from the model.
"""

from pathlib import Path

from . import coverage, git, guard, patch, sandbox, secrets, tools, verdict

RUNS = 3
STACKS = ("backend", "frontend")


def _stack_of(path: str) -> str | None:
    head = path.split("/", 1)[0]
    return head if head in STACKS else None


def _outcomes(result: dict) -> list[dict]:
    return result.get("tests") or []


def _report_path(stack: str, out_dir: Path) -> Path:
    return out_dir / ("coverage.xml" if stack == "backend" else "cov/lcov.info")


def _revert_check(root: Path, ctx: dict, stack: str, test_files: list[str], new_ids: list[str], runner, out_dir) -> dict:
    """Run the new tests against the changed source files as they were before the pull request."""
    modified = [f["path"] for f in ctx["files"] if f["stack"] == stack and f["kind"] == "source" and f["status"] == "M"]
    if ctx.get("mode") == "backfill":
        return {"checked": False, "reason": "backfill: the existing code has no previous version to revert to"}
    if not new_ids:
        return {"checked": False, "reason": "no new tests"}
    if not modified:
        return {"checked": False, "reason": "the pull request only adds new source files, there is nothing to revert"}
    saved = {}
    try:
        for path in modified:
            saved[path] = (root / path).read_bytes()
            (root / path).write_text(git.run(root, "show", f"{ctx['base']}:{path}"))
        result = runner(root, stack, test_files, coverage=False, out_dir=out_dir)
    finally:
        for path, content in saved.items():
            (root / path).write_bytes(content)
    outcome = {t["id"]: t["outcome"] for t in _outcomes(result)}
    weak = [i for i in new_ids if outcome.get(i) == "passed"]
    return {"checked": True, "detect": len(new_ids) - len(weak), "total": len(new_ids), "weak": weak}


def _verify_stack(root, ctx, stack, patch_files, baseline, runner, measure, out_root) -> dict:
    runs, reports = [], []
    for index in range(1, RUNS + 1):
        out_dir = sandbox.prepare_out_dir(out_root / f"{stack}-run{index}")
        result = runner(root, stack, [], coverage=index == 1, out_dir=out_dir)
        runs.append(result)
        reports.append(out_dir)
    failed_runs = [r for r in runs if r.get("error") or r.get("counts") is None]
    if failed_runs:
        return {"ok": False, "counts": None, "runs": [], "error": failed_runs[0].get("error", "a run produced no report")}

    judged = verdict.evaluate(_outcomes(baseline), [_outcomes(r) for r in runs], set(patch_files),
                              lambda test_id: verdict.test_file(root, stack, test_id))
    stack_files = [p for p in patch_files if _stack_of(p) == stack]
    out = {
        "ok": judged["ok"],
        "counts": runs[0]["counts"],
        "runs": [r["counts"] for r in runs],
        "new_tests": len(judged["new_tests"]),
        "new_test_ids": judged["new_tests"],
        "failing": judged["failing"],
        "removed": judged["removed"],
        "flaky": judged["flaky"],
        "broken_by_patch": judged["broken_by_patch"],
        "breaks_existing": judged["breaks_existing"],
        "ids_changed": judged["ids_changed"],
        "coverage": None,
    }
    try:
        out["coverage"] = measure(root, _report_path(stack, reports[0]), ctx["base"], stack=stack)
    except Exception as error:  # a coverage tool failure is information, not a verdict
        out["coverage_error"] = str(error)[:300]
    revert_dir = sandbox.prepare_out_dir(out_root / f"{stack}-revert")
    out["revert"] = _revert_check(root, ctx, stack, stack_files, judged["new_tests"], runner, revert_dir)
    return out


def _without_proposal(root: Path, ctx: dict, runner, out_root: Path) -> dict:
    """No tests were proposed, but the pull request itself may break existing ones: run the suite once."""
    stacks = {}
    for stack in ctx["stacks"]:
        result = runner(root, stack, [], coverage=False, out_dir=sandbox.prepare_out_dir(out_root / f"{stack}-baseline"))
        if result.get("error") or result.get("counts") is None:
            return {"status": "error", "patch_files": [], "stacks": {}, "warnings": [],
                    "reason": f"the {stack} tests could not be run: {result.get('error', '')}"}
        broken = sorted(t["id"] for t in _outcomes(result) if t["outcome"] in ("failed", "error"))
        stacks[stack] = {"ok": True, "counts": result["counts"], "runs": [], "new_tests": 0, "new_test_ids": [],
                         "failing": [], "flaky": [], "broken_by_patch": [], "breaks_existing": broken,
                         "ids_changed": False, "coverage": None, "revert": {"checked": False, "reason": "no new tests"}}
    return {"status": "verified", "patch_files": [], "stacks": stacks, "warnings": []}


def verify(root: Path, ctx: dict, patch_text: str, *, runner=tools.run_stack, scanner=secrets.scan,
           measure=coverage.changed_lines, out_root: Path | None = None) -> dict:
    root = Path(root)
    if not patch_text.strip():
        return _without_proposal(root, ctx, runner, Path(out_root) if out_root else root.parent / "test-agent-out")

    checked = guard.check(patch_text)
    if checked.violations:
        return {"status": "rejected", "patch_files": [], "stacks": {}, "warnings": checked.warnings,
                "reason": "; ".join(checked.violations)}

    patch_files = patch.changed_paths(patch_text)
    out_root = Path(out_root) if out_root else root.parent / "test-agent-out"
    stacks = [s for s in STACKS if s in ctx["stacks"] or any(_stack_of(p) == s for p in patch_files)]

    baselines = {}
    for stack in stacks:
        result = runner(root, stack, [], coverage=False, out_dir=sandbox.prepare_out_dir(out_root / f"{stack}-baseline"))
        if result.get("error") or result.get("counts") is None:
            return {"status": "error", "patch_files": [], "stacks": {}, "warnings": checked.warnings,
                    "reason": f"the baseline run of {stack} produced no report: {result.get('error', '')}"}
        baselines[stack] = result

    try:
        patch.apply(root, patch_text)
    except (patch.PatchError, git.GitError) as error:
        return {"status": "rejected", "patch_files": [], "stacks": {}, "warnings": checked.warnings, "reason": str(error)}

    existing = [p for p in patch_files if (root / p).is_file()]
    findings = scanner(root, existing)
    if findings:
        rules = ", ".join(sorted({f["rule"] for f in findings}))
        return {"status": "rejected", "patch_files": [], "stacks": {}, "warnings": checked.warnings,
                "reason": f"secret scan found: {rules}"}

    results = {stack: _verify_stack(root, ctx, stack, patch_files, baselines[stack], runner, measure, out_root)
               for stack in stacks}
    return {"status": "verified" if all(r["ok"] for r in results.values()) else "failing",
            "patch_files": patch_files, "stacks": results, "warnings": checked.warnings}
