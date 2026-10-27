import subprocess

import pytest

from test_agent import git


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(cwd)})


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("one\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _plant_traps(repo, marker):
    """What test code with write access to .git could do: run a command on every git invocation."""
    script = repo / "trap.sh"
    script.write_text(f"#!/bin/sh\necho ran >> {marker}\n")
    script.chmod(0o755)
    _git(repo, "config", "core.fsmonitor", str(script))
    _git(repo, "config", "diff.external", str(script))
    hooks = repo / ".git" / "hooks"
    hook = hooks / "post-index-change"
    hook.write_text(f"#!/bin/sh\necho ran >> {marker}\n")
    hook.chmod(0o755)


def test_run_returns_stdout(repo):
    assert git.run(repo, "log", "--format=%s") .strip() == "base"


def test_planted_config_and_hooks_do_not_run(repo, tmp_path_factory):
    marker = tmp_path_factory.mktemp("marker") / "ran.txt"
    _plant_traps(repo, marker)
    (repo / "a.txt").write_text("two\n")
    (repo / "b.txt").write_text("new\n")
    git.run(repo, "add", "-N", "--", "b.txt")
    diff = git.run(repo, "diff", "--binary", "--no-ext-diff", "--no-textconv")
    git.run(repo, "status", "--porcelain")
    assert "+two" in diff
    assert not marker.exists()


def test_plain_git_would_have_run_the_trap(repo, tmp_path_factory):
    """Guards the test above: the trap is real, so the wrapper is what stops it."""
    marker = tmp_path_factory.mktemp("marker") / "ran.txt"
    _plant_traps(repo, marker)
    (repo / "a.txt").write_text("two\n")
    subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True,
                   env={"PATH": "/usr/bin:/bin", "HOME": str(repo)})
    assert marker.exists()


def test_a_failing_command_raises_with_the_message(repo):
    with pytest.raises(git.GitError, match="rev-parse --verify .* failed"):
        git.run(repo, "rev-parse", "--verify", "does-not-exist^{commit}")
