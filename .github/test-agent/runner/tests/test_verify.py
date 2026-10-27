import subprocess

import pytest

from test_agent import verify

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}

GOOD_PATCH = (
    "diff --git a/backend/tests/test_new.py b/backend/tests/test_new.py\nnew file mode 100644\n"
    "--- /dev/null\n+++ b/backend/tests/test_new.py\n@@ -0,0 +1,2 @@\n+def test_new():\n+    assert 1\n"
)
BAD_PATCH = GOOD_PATCH.replace("backend/tests/test_new.py", "backend/app/new.py")
SKIP_PATCH = GOOD_PATCH.replace("+def test_new():", "+@pytest.mark.skip\n+def test_new():").replace("@@ -0,0 +1,2 @@", "@@ -0,0 +1,3 @@")


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**ENV, "HOME": str(cwd)}).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "backend/app").mkdir(parents=True)
    (tmp_path / "backend/tests").mkdir(parents=True)
    (tmp_path / "backend/tests/test_old.py").write_text("def test_old():\n    assert 1\n")
    (tmp_path / "backend/app/x.py").write_text("def f():\n    return 1\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "backend/app/x.py").write_text("def f():\n    return 2\n")
    _git(tmp_path, "commit", "-qam", "change")
    ctx = {"base": base, "stacks": ["backend"], "should_run": True, "files": [
        {"path": "backend/app/x.py", "stack": "backend", "kind": "source", "status": "M"}]}
    return tmp_path, ctx


def case(outcome, test_id):
    return {"id": test_id, "outcome": outcome, "message": ""}


OLD = "tests.test_old::test_old"
NEW = "tests.test_new::test_new"


def run_result(*tests, ok=True):
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for t in tests:
        counts[t["outcome"]] += 1
    return {"stack": "backend", "ok": ok, "counts": counts, "tests": list(tests), "output": ""}


class ScriptedRunner:
    """Answers run_stack calls in order and records them."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, root, stack, paths, *, coverage, out_dir, timeout=600):
        self.calls.append({"stack": stack, "paths": paths, "coverage": coverage})
        return self.results.pop(0)


def no_secrets(root, files, **_):
    return []


def full_coverage(root, report, base, stack="backend"):
    return {"covered": 2, "total": 2, "percent": 100.0, "files": {}}


def go(repo, patch_text, runner, *, scanner=no_secrets, measure=full_coverage):
    root, ctx = repo
    return verify.verify(root, ctx, patch_text, runner=runner, scanner=scanner, measure=measure,
                         out_root=root.parent / "out")


def healthy_runner():
    base = run_result(case("passed", OLD))
    after = run_result(case("passed", OLD), case("passed", NEW))
    reverted = run_result(case("failed", NEW))
    return ScriptedRunner(base, after, after, after, reverted)


def test_an_empty_patch_needs_no_verification(repo):
    runner = ScriptedRunner()
    assert go(repo, "", runner) == {"status": "verified", "patch_files": [], "stacks": {}, "warnings": []}
    assert runner.calls == []


def test_a_patch_that_the_guard_rejects_never_reaches_a_test_run(repo):
    for patch_text, expected in ((BAD_PATCH, "backend/app/new.py"), (SKIP_PATCH, "weaken")):
        runner = ScriptedRunner()
        result = go(repo, patch_text, runner)
        assert result["status"] == "rejected" and expected in result["reason"]
        assert runner.calls == []
    assert not (repo[0] / "backend/app/new.py").exists()


def test_a_healthy_proposal_is_verified_with_three_runs_coverage_and_a_revert_check(repo):
    runner = healthy_runner()
    result = go(repo, GOOD_PATCH, runner)
    stack = result["stacks"]["backend"]
    assert result["status"] == "verified" and result["patch_files"] == ["backend/tests/test_new.py"]
    assert [c["coverage"] for c in runner.calls[:4]] == [False, True, False, False]
    assert stack["ok"] is True and stack["new_tests"] == 1 and len(stack["runs"]) == 3
    assert stack["coverage"]["percent"] == 100.0
    assert stack["revert"] == {"checked": True, "detect": 1, "total": 1, "weak": []}


def test_the_baseline_is_measured_before_the_patch_is_applied(repo):
    runner = healthy_runner()
    original = runner.__call__

    def spy(root, stack, paths, **kw):
        spy.seen.append((root / "backend/tests/test_new.py").exists())
        return original(root, stack, paths, **kw)

    spy.seen = []
    go(repo, GOOD_PATCH, spy)
    assert spy.seen[0] is False and all(spy.seen[1:])


def test_a_new_test_that_fails_makes_the_proposal_fail(repo):
    base = run_result(case("passed", OLD))
    bad = run_result(case("passed", OLD), case("failed", NEW), ok=False)
    result = go(repo, GOOD_PATCH, ScriptedRunner(base, bad, bad, bad, run_result(case("failed", NEW))))
    assert result["status"] == "failing" and result["stacks"]["backend"]["failing"] == [NEW]


def test_failures_that_already_existed_are_reported_and_do_not_fail_the_proposal(repo):
    base = run_result(case("failed", OLD), ok=False)
    after = run_result(case("failed", OLD), case("passed", NEW), ok=False)
    result = go(repo, GOOD_PATCH, ScriptedRunner(base, after, after, after, run_result(case("failed", NEW))))
    assert result["status"] == "verified"
    assert result["stacks"]["backend"]["breaks_existing"] == [OLD]


def test_a_secret_in_the_patch_rejects_it_before_tests_run(repo):
    runner = ScriptedRunner(run_result(case("passed", OLD)))
    result = go(repo, GOOD_PATCH, runner,
                scanner=lambda root, files, **_: [{"file": files[0], "rule": "anthropic-api-key", "line": 1}])
    assert result["status"] == "rejected" and "anthropic-api-key" in result["reason"]
    assert len(runner.calls) == 1  # only the baseline ran


def test_a_coverage_tool_failure_is_recorded_without_failing_the_proposal(repo):
    def broken(*args, **kwargs):
        raise RuntimeError("diff-cover exploded")
    result = go(repo, GOOD_PATCH, healthy_runner(), measure=broken)
    assert result["status"] == "verified"
    assert result["stacks"]["backend"]["coverage"] is None
    assert "diff-cover exploded" in result["stacks"]["backend"]["coverage_error"]


def test_tests_that_pass_on_the_reverted_source_are_listed_as_weak(repo):
    base = run_result(case("passed", OLD))
    after = run_result(case("passed", OLD), case("passed", NEW))
    result = go(repo, GOOD_PATCH, ScriptedRunner(base, after, after, after, run_result(case("passed", NEW))))
    revert = result["stacks"]["backend"]["revert"]
    assert revert["detect"] == 0 and revert["weak"] == [NEW]
    assert result["status"] == "verified"


def test_the_source_files_are_restored_after_the_revert_check(repo):
    go(repo, GOOD_PATCH, healthy_runner())
    assert "return 2" in (repo[0] / "backend/app/x.py").read_text()


def test_the_revert_check_runs_only_the_proposed_test_files(repo):
    runner = healthy_runner()
    go(repo, GOOD_PATCH, runner)
    assert runner.calls[4]["paths"] == ["backend/tests/test_new.py"]


def test_new_units_without_a_base_version_skip_the_revert_check(repo):
    root, ctx = repo
    ctx["files"][0]["status"] = "A"
    base = run_result(case("passed", OLD))
    after = run_result(case("passed", OLD), case("passed", NEW))
    runner = ScriptedRunner(base, after, after, after)
    result = verify.verify(root, ctx, GOOD_PATCH, runner=runner, scanner=no_secrets, measure=full_coverage,
                           out_root=root.parent / "out")
    assert result["stacks"]["backend"]["revert"]["checked"] is False
    assert len(runner.calls) == 4


def test_a_missing_report_in_the_baseline_is_an_error_not_a_pass(repo):
    broken = {"stack": "backend", "ok": False, "counts": None, "tests": [], "error": "test report is missing"}
    result = go(repo, GOOD_PATCH, ScriptedRunner(broken))
    assert result["status"] == "error" and "test report is missing" in result["reason"]
