import subprocess

import pytest

from test_agent import verify

CTX = {"stacks": ["backend", "frontend"], "should_run": True}

GOOD_PATCH = (
    "diff --git a/backend/tests/test_new.py b/backend/tests/test_new.py\nnew file mode 100644\n"
    "--- /dev/null\n+++ b/backend/tests/test_new.py\n@@ -0,0 +1,2 @@\n+def test_new():\n+    assert 1\n"
)
BAD_PATCH = GOOD_PATCH.replace("backend/tests/test_new.py", "backend/app/new.py")


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "backend/tests").mkdir(parents=True)
    (tmp_path / "backend/tests/__init__.py").write_text("")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=tmp_path, check=True, env=env)
    return tmp_path


def _runner(results):
    calls = []

    def run(root, stack, paths, *, coverage, out_dir, timeout=600):
        calls.append((stack, paths, coverage))
        return results[stack]

    run.calls = calls
    return run


PASS = {"ok": True, "counts": {"passed": 3, "failed": 0, "error": 0, "skipped": 0}, "tests": []}
FAIL = {"ok": False, "counts": {"passed": 2, "failed": 1, "error": 0, "skipped": 0}, "tests": []}


def test_an_empty_patch_needs_no_verification(repo):
    runner = _runner({})
    result = verify.verify(repo, CTX, "", runner=runner, out_root=repo / "o")
    assert result == {"status": "verified", "patch_files": [], "stacks": {}}
    assert runner.calls == []


def test_a_passing_patch_is_verified_for_every_affected_stack(repo):
    runner = _runner({"backend": PASS, "frontend": PASS})
    result = verify.verify(repo, CTX, GOOD_PATCH, runner=runner, out_root=repo / "o")
    assert result["status"] == "verified"
    assert result["patch_files"] == ["backend/tests/test_new.py"]
    assert set(result["stacks"]) == {"backend", "frontend"}
    assert (repo / "backend/tests/test_new.py").exists()


def test_a_failing_stack_makes_the_proposal_fail(repo):
    runner = _runner({"backend": FAIL, "frontend": PASS})
    result = verify.verify(repo, CTX, GOOD_PATCH, runner=runner, out_root=repo / "o")
    assert result["status"] == "failing"
    assert result["stacks"]["backend"]["ok"] is False


def test_a_patch_outside_the_writable_area_is_rejected_before_any_test_runs(repo):
    runner = _runner({"backend": PASS, "frontend": PASS})
    result = verify.verify(repo, CTX, BAD_PATCH, runner=runner, out_root=repo / "o")
    assert result["status"] == "rejected"
    assert "backend/app/new.py" in result["reason"]
    assert runner.calls == []
    assert not (repo / "backend/app/new.py").exists()
