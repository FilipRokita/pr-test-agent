import json

from test_agent import backfill

COVERAGE_JSON = json.dumps({
    "files": {
        "app/api/health.py": {"summary": {"percent_covered": 0.0, "num_statements": 9}, "missing_lines": [1, 2, 3, 4, 5, 6, 7, 8, 9]},
        "app/features/todos/router.py": {"summary": {"percent_covered": 51.0, "num_statements": 29}, "missing_lines": [24, 25, 26, 27, 32]},
        "app/features/todos/mappers.py": {"summary": {"percent_covered": 100.0, "num_statements": 4}, "missing_lines": []},
    },
    "totals": {"percent_covered": 42.0, "covered_lines": 64, "num_statements": 145},
})

LCOV = "\n".join([
    "TN:", "SF:src/lib/http.ts", "DA:1,0", "DA:2,0", "DA:3,1", "end_of_record",
    "SF:src/hooks/useNotice.ts", "DA:1,1", "DA:2,1", "end_of_record",
    "SF:src/app/AppProviders.tsx", "DA:1,0", "end_of_record", ""])


def test_backend_gaps_are_the_files_with_uncovered_lines_largest_first():
    gaps = backfill.backend_gaps(COVERAGE_JSON)
    assert [g["path"] for g in gaps] == ["backend/app/api/health.py", "backend/app/features/todos/router.py"]
    assert gaps[0] == {"path": "backend/app/api/health.py", "stack": "backend", "coverage_percent": 0.0,
                       "uncovered_lines": [1, 2, 3, 4, 5, 6, 7, 8, 9]}


def test_frontend_gaps_come_from_lcov_with_repository_paths():
    gaps = backfill.frontend_gaps(LCOV)
    assert [g["path"] for g in gaps] == ["frontend/src/lib/http.ts", "frontend/src/app/AppProviders.tsx"]
    assert gaps[0]["coverage_percent"] == 33.3 and gaps[0]["uncovered_lines"] == [1, 2]


def test_totals_are_read_for_the_before_and_after_comparison():
    assert backfill.backend_total(COVERAGE_JSON) == 42.0
    assert backfill.frontend_total(LCOV) == 50.0


def test_the_file_list_narrows_the_gaps():
    gaps = backfill.backend_gaps(COVERAGE_JSON)
    assert [g["path"] for g in backfill.select(gaps, ["backend/app/api/health.py"])] == ["backend/app/api/health.py"]
    assert backfill.select(gaps, None) == gaps


def test_the_task_lists_the_gaps_and_says_it_is_a_backfill():
    task = backfill.render_task("backend", backfill.backend_gaps(COVERAGE_JSON))
    assert "Mode: backfill. Stacks: backend." in task
    assert '"path": "backend/app/api/health.py"' in task and "<coverage_gaps>" in task
    assert "mappers.py" not in task


def test_the_context_for_verification_has_no_revert_check_and_lists_the_files_as_sources():
    ctx = backfill.make_context("backend", backfill.backend_gaps(COVERAGE_JSON), head="a" * 40)
    assert ctx["mode"] == "backfill" and ctx["stacks"] == ["backend"] and ctx["base"] == "a" * 40
    assert all(f["kind"] == "source" for f in ctx["files"])


import subprocess

import pytest

from test_agent import verify

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/a.py").write_text("x = 1\n")
    (tmp_path / "frontend/node_modules").mkdir(parents=True)
    (tmp_path / "frontend/node_modules/dep.js").write_text("dep")
    (tmp_path / "backend/.venv").mkdir()
    (tmp_path / "backend/.venv/marker").write_text("venv")
    (tmp_path / ".gitignore").write_text("node_modules/\n.venv/\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, env={**ENV, "HOME": str(tmp_path)})
    subprocess.run(["git", "commit", "-q", "-m", "b"], cwd=tmp_path, check=True, env={**ENV, "HOME": str(tmp_path)})
    return tmp_path


def test_the_worktree_is_a_separate_copy_with_the_installed_dependencies_linked(repo, tmp_path_factory):
    where = tmp_path_factory.mktemp("wt") / "tree"
    with backfill.worktree(repo, where) as tree:
        assert (tree / "backend/a.py").read_text() == "x = 1\n"
        assert (tree / "frontend/node_modules/dep.js").read_text() == "dep"
        assert (tree / "backend/.venv/marker").read_text() == "venv"
        (tree / "backend/a.py").write_text("changed\n")
    assert (repo / "backend/a.py").read_text() == "x = 1\n"
    assert not where.exists()


def test_a_backfill_has_no_previous_version_to_revert_to(repo):
    ctx = backfill.make_context("backend", [_gap_for("backend/a.py")], head="a" * 40)
    reverted = verify._revert_check(repo, ctx, "backend", ["backend/tests/test_x.py"], ["tests.test_x::t"],
                                    runner=lambda *a, **k: pytest.fail("must not run"), out_dir=repo)
    assert reverted["checked"] is False and "backfill" in reverted["reason"]


def _gap_for(path):
    return {"path": path, "stack": "backend", "coverage_percent": 0.0, "uncovered_lines": [1]}


def test_the_coverage_after_a_backfill_is_the_total_of_the_report(tmp_path):
    (tmp_path / "coverage.json").write_text(COVERAGE_JSON)
    (tmp_path / "coverage.xml").write_text("<x/>")
    assert backfill.measure(None, tmp_path / "coverage.xml", "a" * 40, stack="backend")["percent"] == 42.0
    (tmp_path / "cov").mkdir()
    (tmp_path / "cov/lcov.info").write_text(LCOV)
    assert backfill.measure(None, tmp_path / "cov/lcov.info", "a" * 40, stack="frontend")["percent"] == 50.0


def test_the_pull_request_text_shows_before_and_after_and_escapes_model_text():
    result = {"summary": "@x <b>done</b>", "decisions": [
        {"file": "backend/app/a.py", "action": "add", "reason": "r | pipe", "test_files": ["backend/tests/test_a.py"]}],
        "findings": [{"kind": "suspected_bug", "file": "backend/app/a.py", "description": "looks wrong"}], "warnings": []}
    verification = {"status": "verified", "patch_files": ["backend/tests/test_a.py"], "warnings": [],
                    "stacks": {"backend": {"counts": {"passed": 40, "failed": 0, "error": 0, "skipped": 0}}}}
    text = backfill.report_markdown("backend", before=42.0, after=91.5, agent={"skills_used": ["analyze-changes"],
                                    "turns": 30, "cost_usd": 1.2, "duration_s": 300, "model": "m"},
                                    result=result, verification=verification)
    assert "42.0%" in text and "91.5%" in text and "40 passed" in text
    assert "<b>" not in text and "suspected" in text and "analyze" in text
