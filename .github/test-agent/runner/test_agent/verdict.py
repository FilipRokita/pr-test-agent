"""Per-test verdict over a baseline run and several runs with the patch applied."""

from pathlib import Path


def test_file(root: Path | str, stack: str, test_id: str) -> str:
    """Repository-relative file of a JUnit test id (pytest: dotted module, Vitest: file path)."""
    location = test_id.split("::", 1)[0]
    if stack == "frontend":
        return f"frontend/{location}"
    parts = location.split(".")
    while len(parts) > 1:
        candidate = f"backend/{'/'.join(parts)}.py"
        if (Path(root) / candidate).exists():
            return candidate
        parts.pop()
    return f"backend/{location.replace('.', '/')}.py"


def evaluate(baseline: list[dict], runs: list[list[dict]], touched_files: set[str], file_of) -> dict:
    base = {t["id"]: t["outcome"] for t in baseline}
    maps = [{t["id"]: t["outcome"] for t in run} for run in runs]
    everything = set(base).union(*maps)
    touched = {i for i in everything if file_of(i) in touched_files}

    untouched_before = {i for i in base if i not in touched}
    untouched_after = {i for i in maps[0] if i not in touched}
    ids_changed = untouched_before != untouched_after

    # A touched test that was already failing at baseline and still fails is the pull request's regression, not the
    # proposal's fault. A test that is gone from every run was removed or renamed; that is shown, but it is not a failure.
    failing = sorted(i for i in touched if base.get(i, "passed") == "passed"
                     and any(i in m and m[i] != "passed" for m in maps))
    removed = sorted(i for i in touched if i in base and not any(i in m for m in maps))
    flaky = sorted(i for i in everything if len({m.get(i) for m in maps}) > 1)
    broken = sorted(i for i in untouched_after if base.get(i) == "passed" and any(m.get(i) != "passed" for m in maps)
                    and i not in flaky)
    still_failing = {i for i in base if i in touched and base[i] in ("failed", "error") and maps[0].get(i) in ("failed", "error")}
    breaks_existing = sorted({i for i in untouched_before if base[i] in ("failed", "error")} | still_failing)
    return {
        "ok": not (failing or flaky or broken or ids_changed),
        "new_tests": sorted(i for i in maps[0] if i not in base),
        "failing": failing,
        "removed": removed,
        "flaky": flaky,
        "broken_by_patch": broken,
        "breaks_existing": breaks_existing,
        "ids_changed": ids_changed,
    }
