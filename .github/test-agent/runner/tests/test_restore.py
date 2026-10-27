import subprocess

import pytest

from test_agent import proposal, restore

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}

DIFF = (
    "diff --git a/backend/tests/test_new.py b/backend/tests/test_new.py\nnew file mode 100644\n"
    "--- /dev/null\n+++ b/backend/tests/test_new.py\n@@ -0,0 +1,2 @@\n+def test_new():\n+    assert 1\n"
)


class FakeGh:
    def __init__(self, tip_email, diff=DIFF, branch=True):
        self.tip_email, self.diff, self.branch, self.calls = tip_email, diff, branch, []

    def __call__(self, args, body=None):
        self.calls.append(args)
        url = args[-1]
        if url.endswith("/branches/test-agent/pr-9"):
            if not self.branch:
                raise RuntimeError("gh api failed: HTTP 404 Not Found")
            return f'{{"commit": {{"sha": "{"d" * 40}", "commit": {{"author": {{"email": "{self.tip_email}"}}}}}}}}'
        if "/commits/" in url:
            return self.diff
        raise AssertionError(url)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "backend/tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "backend/tests/test_old.py").write_text("def test_old():\n    assert 1\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, env={**ENV, "HOME": str(tmp_path)})
    subprocess.run(["git", "commit", "-q", "-m", "b"], cwd=tmp_path, check=True, env={**ENV, "HOME": str(tmp_path)})
    return tmp_path


def test_the_previous_bot_proposal_is_put_back_in_the_working_tree(repo):
    assert restore.restore(repo, "o/r", 9, run=FakeGh(proposal.BOT_EMAIL)) == "restored"
    assert (repo / "backend/tests/test_new.py").exists()


def test_a_branch_with_human_commits_is_not_restored(repo):
    assert restore.restore(repo, "o/r", 9, run=FakeGh("someone@example.com")) == "not restored: the branch has human commits"
    assert not (repo / "backend/tests/test_new.py").exists()


def test_no_previous_branch_means_a_clean_start(repo):
    assert restore.restore(repo, "o/r", 9, run=FakeGh("", branch=False)) == "nothing to restore"


def test_a_proposal_that_does_not_apply_any_more_means_a_clean_start(repo):
    broken = DIFF.replace("new file mode 100644\n--- /dev/null", "index 1..2 100644\n--- a/backend/tests/test_missing.py").replace("b/backend/tests/test_new.py\n@@", "b/backend/tests/test_new.py\n@@")
    result = restore.restore(repo, "o/r", 9, run=FakeGh(proposal.BOT_EMAIL, diff=broken))
    assert result.startswith("not restored")


def test_a_proposal_touching_other_files_is_never_applied(repo):
    evil = DIFF.replace("backend/tests/test_new.py", "backend/app/x.py")
    result = restore.restore(repo, "o/r", 9, run=FakeGh(proposal.BOT_EMAIL, diff=evil))
    assert result.startswith("not restored")
    assert not (repo / "backend/app/x.py").exists()
