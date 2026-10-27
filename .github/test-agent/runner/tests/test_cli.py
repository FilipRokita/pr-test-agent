import json
import subprocess

import pytest

from test_agent.__main__ import main

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**ENV, "HOME": str(cwd)}).stdout.strip()


@pytest.fixture
def pr(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "backend/app").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "backend/app/x.py").write_text("def f():\n    return 1\n")
    (repo / "README.md").write_text("hi\n")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "-q", "-c", "feature")
    (repo / "backend/app/x.py").write_text("def f():\n    return 2\n")
    (repo / "README.md").write_text("changed\n")
    _git(repo, "commit", "-qam", "change")
    head = _git(repo, "rev-parse", "HEAD")
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {
        "number": 9, "title": "Change f", "body": "returns 2 now",
        "base": {"sha": base}, "head": {"sha": head}}}))
    output = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    return repo, tmp_path / "artifacts", output


def test_context_command_writes_the_context_and_the_run_flag(pr):
    repo, artifacts, output = pr
    assert main(["context", "--root", str(repo), "--artifacts", str(artifacts)]) == 0
    ctx = json.loads((artifacts / "context.json").read_text())
    assert ctx["should_run"] is True and ctx["stacks"] == ["backend"] and ctx["pull_request"] == 9
    assert "return 2" in ctx["diff"] and "README" not in ctx["diff"]
    assert "should_run=true" in output.read_text()


def test_generate_without_credentials_skips_cleanly(pr, monkeypatch):
    repo, artifacts, _ = pr
    main(["context", "--root", str(repo), "--artifacts", str(artifacts)])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert main(["generate", "--root", str(repo), "--artifacts", str(artifacts)]) == 0
    assert json.loads((artifacts / "agent-result.json").read_text()) == {"status": "skipped_no_credentials"}


def test_a_docs_only_change_does_not_start_the_agent(pr):
    repo, artifacts, output = pr
    _git(repo, "reset", "-q", "--hard", "HEAD~1")
    (repo / "README.md").write_text("docs only\n")
    _git(repo, "commit", "-qam", "docs")
    event = json.loads(open(__import__("os").environ["GITHUB_EVENT_PATH"]).read())
    base = _git(repo, "rev-parse", "HEAD~1")
    event["pull_request"].update(head={"sha": _git(repo, "rev-parse", "HEAD")}, base={"sha": base})
    open(__import__("os").environ["GITHUB_EVENT_PATH"], "w").write(json.dumps(event))
    main(["context", "--root", str(repo), "--artifacts", str(artifacts)])
    assert "should_run=false" in output.read_text()
