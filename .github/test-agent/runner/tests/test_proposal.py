import subprocess

import pytest

from test_agent import git, proposal

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}

PATCH = (
    "diff --git a/backend/tests/test_new.py b/backend/tests/test_new.py\nnew file mode 100644\n"
    "--- /dev/null\n+++ b/backend/tests/test_new.py\n@@ -0,0 +1,2 @@\n+def test_new():\n+    assert 1\n"
)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**ENV, "HOME": str(cwd)}).stdout.strip()


@pytest.fixture
def remote_and_clone(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(remote), str(clone))
    (clone / "backend/tests").mkdir(parents=True)
    (clone / "backend/tests/test_old.py").write_text("def test_old():\n    assert 1\n")
    _git(clone, "add", "-A"); _git(clone, "commit", "-q", "-m", "base"); _git(clone, "push", "-q", "origin", "main")
    return remote, clone


def test_the_proposal_is_one_bot_commit_on_the_head_of_the_pull_request(remote_and_clone):
    remote, clone = remote_and_clone
    head = _git(clone, "rev-parse", "HEAD")
    sha = proposal.commit(clone, head, "test-agent/pr-9", PATCH, "Add tests for #9")
    assert _git(clone, "rev-parse", f"{sha}^") == head
    assert _git(clone, "log", "-1", "--format=%an <%ae>", sha) == f"{proposal.BOT_NAME} <{proposal.BOT_EMAIL}>"
    assert _git(clone, "show", "--name-only", "--format=", sha) == "backend/tests/test_new.py"
    assert (clone / "backend/tests/test_new.py").exists()


def test_pushing_replaces_the_previous_proposal(remote_and_clone):
    remote, clone = remote_and_clone
    head = _git(clone, "rev-parse", "HEAD")
    first = proposal.commit(clone, head, "test-agent/pr-9", PATCH, "first")
    proposal.push(clone, "test-agent/pr-9", str(remote))
    second_patch = PATCH.replace("assert 1", "assert 2")
    second = proposal.commit(clone, head, "test-agent/pr-9", second_patch, "second")
    proposal.push(clone, "test-agent/pr-9", str(remote))
    assert _git(remote, "rev-parse", "test-agent/pr-9") == second != first
    assert _git(remote, "rev-list", "--count", f"main..test-agent/pr-9") == "1"


def test_a_patch_outside_the_writable_area_is_never_committed(remote_and_clone):
    remote, clone = remote_and_clone
    head = _git(clone, "rev-parse", "HEAD")
    with pytest.raises(Exception, match="outside the writable"):
        proposal.commit(clone, head, "test-agent/pr-9", PATCH.replace("backend/tests/test_new.py", "backend/app/x.py"), "x")


def test_the_author_check_recognises_only_the_bot():
    assert proposal.is_bot_email(proposal.BOT_EMAIL) is True
    assert proposal.is_bot_email("someone@example.com") is False
    assert proposal.is_bot_email("") is False
