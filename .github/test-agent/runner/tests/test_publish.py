import subprocess

import pytest

from test_agent import proposal, publish, report

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}

PATCH = (
    "diff --git a/backend/tests/test_new.py b/backend/tests/test_new.py\nnew file mode 100644\n"
    "--- /dev/null\n+++ b/backend/tests/test_new.py\n@@ -0,0 +1,2 @@\n+def test_new():\n+    assert 1\n"
)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**ENV, "HOME": str(cwd)}).stdout.strip()


class FakeGithub:
    """What publish needs from GitHub, recording the writes."""

    def __init__(self, stacked=None, tip_email=None):
        self.stacked, self.tip_email, self.calls = stacked, tip_email, []

    def open_stacked(self, branch):
        return self.stacked

    def branch_tip_email(self, branch):
        return self.tip_email

    def create_pr(self, **kw):
        self.calls.append(("create", kw)); return 21

    def update_pr(self, number, **kw):
        self.calls.append(("update", number, kw))

    def close_pr(self, number, comment):
        self.calls.append(("close", number, comment))

    def upsert_comment(self, pr, body):
        self.calls.append(("comment", pr, body))


@pytest.fixture
def env(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(remote), str(clone))
    (clone / "backend/tests").mkdir(parents=True)
    (clone / "backend/tests/test_old.py").write_text("def test_old():\n    assert 1\n")
    _git(clone, "add", "-A"); _git(clone, "commit", "-q", "-m", "base"); _git(clone, "push", "-q", "origin", "main")
    head = _git(clone, "rev-parse", "HEAD")
    ctx = {"should_run": True, "pull_request": 9, "head": head, "base": head, "title": "Count things",
           "head_ref": "feature", "files": [], "stacks": ["backend"]}
    return remote, clone, ctx


AGENT = {"status": "ok", "skills_used": [], "turns": 1, "duration_s": 1, "cost_usd": 0, "model": "m", "denials": [],
         "problems": [], "structured_output": {"summary": "Added a test.", "decisions": [], "findings": [], "warnings": []}}
VERIFIED = {"status": "verified", "patch_files": ["backend/tests/test_new.py"], "stacks": {}, "warnings": []}


def run(env, gh, verification=VERIFIED, patch_text=PATCH, agent=AGENT):
    remote, clone, ctx = env
    return publish.publish(clone, ctx, agent, verification, patch_text, gh=gh, remote=str(remote), run_url="u")


def test_a_verified_proposal_is_pushed_and_opens_a_stacked_pull_request_against_the_feature_branch(env):
    gh = FakeGithub()
    result = run(env, gh)
    assert result["action"] == "create" and result["stacked"] == 21
    kind, kw = gh.calls[0]
    assert kind == "create" and kw["base"] == "feature" and kw["head"] == "test-agent/pr-9"
    assert _git(env[0], "rev-parse", "test-agent/pr-9") == _git(env[1], "rev-parse", "HEAD")
    comment = [c for c in gh.calls if c[0] == "comment"][0]
    assert comment[1] == 9 and "#21" in comment[2]


def test_a_later_run_updates_the_open_pull_request_in_place(env):
    gh = FakeGithub(stacked={"number": 21}, tip_email=proposal.BOT_EMAIL)
    result = run(env, gh)
    assert result["action"] == "update"
    assert [c[0] for c in gh.calls if c[0] != "comment"] == ["update"]


def test_human_commits_on_the_test_branch_block_the_push_and_say_so(env):
    gh = FakeGithub(stacked={"number": 21}, tip_email="someone@example.com")
    result = run(env, gh)
    assert result["action"] == "blocked"
    assert subprocess.run(["git", "rev-parse", "--verify", "test-agent/pr-9"], cwd=env[0], capture_output=True).returncode != 0
    assert "human" in [c for c in gh.calls if c[0] == "comment"][0][2]


def test_a_proposal_that_no_longer_passes_closes_the_old_pull_request_with_the_reason(env):
    gh = FakeGithub(stacked={"number": 21}, tip_email=proposal.BOT_EMAIL)
    result = run(env, gh, verification={"status": "failing", "patch_files": [], "stacks": {}, "warnings": []}, patch_text="")
    assert result["action"] == "close"
    assert gh.calls[0][0] == "close" and "superseded" in gh.calls[0][2]


def test_nothing_is_written_when_the_run_was_skipped_or_failed(env):
    gh = FakeGithub(stacked={"number": 21}, tip_email=proposal.BOT_EMAIL)
    remote, clone, ctx = env
    result = publish.publish(clone, {**ctx, "should_run": False, "skip_reason": "docs"}, None, None, "",
                             gh=gh, remote=str(remote), run_url="u")
    assert result["action"] == "keep"
    assert [c[0] for c in gh.calls] == ["comment"]


def test_an_unchanged_context_keeps_the_previous_comment(env):
    gh = FakeGithub()
    remote, clone, ctx = env
    publish.publish(clone, {**ctx, "should_run": False, "skip_reason": "x", "keep_previous": True}, None, None, "",
                    gh=gh, remote=str(remote), run_url="u")
    assert gh.calls == []


def test_the_pull_request_text_is_escaped_and_capped(env):
    gh = FakeGithub()
    remote, clone, ctx = env
    publish.publish(clone, {**ctx, "title": "@owner <b>x</b> " + "t" * 400}, AGENT, VERIFIED, PATCH,
                    gh=gh, remote=str(remote), run_url="u")
    created = gh.calls[0][1]
    assert "<" not in created["title"] and ">" not in created["title"] and "\n" not in created["title"]
    assert len(created["title"]) <= 200
    assert created["body"].count(report.MARKER) == 0


def test_cleanup_closes_the_pull_request_and_deletes_the_branch(env):
    class Cleanup(FakeGithub):
        deleted = []

        def delete_branch(self, branch):
            self.deleted.append(branch)

    gh = Cleanup(stacked={"number": 21}, tip_email=proposal.BOT_EMAIL)
    publish.cleanup(env[2], gh=gh)
    assert gh.calls[0][0] == "close" and gh.deleted == ["test-agent/pr-9"]
