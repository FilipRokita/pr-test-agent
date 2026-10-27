import subprocess

import pytest

from test_agent import git, patch


def _commit_all(repo, message="base"):
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(repo)}
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, check=True, env=env)


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    for path, content in {
        "backend/app/x.py": "def f():\n    return 1\n",
        "backend/tests/conftest.py": "# fixtures\n",
        "backend/tests/test_old.py": "def test_old():\n    assert True\n",
        "frontend/src/lib/a.ts": "export const a = 1\n",
        "frontend/src/lib/a.test.ts": "it('a', () => {})\n",
    }.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(content)
    _commit_all(tmp_path)
    return tmp_path


def test_new_and_modified_test_files_are_in_the_patch(repo):
    (repo / "backend/tests/test_new.py").write_text("def test_new():\n    assert 1\n")
    (repo / "backend/tests/test_old.py").write_text("def test_old():\n    assert 1 == 1\n")
    (repo / "frontend/src/lib/a.test.ts").write_text("it('a', () => { expect(1).toBe(1) })\n")
    text = patch.create(repo)
    assert patch.changed_paths(text) == [
        "backend/tests/test_new.py", "backend/tests/test_old.py", "frontend/src/lib/a.test.ts"]


def test_changes_outside_the_writable_area_never_enter_the_patch(repo):
    (repo / "backend/app/x.py").write_text("def f():\n    return 2\n")
    (repo / "backend/tests/conftest.py").write_text("# changed\n")
    (repo / "frontend/src/lib/a.ts").write_text("export const a = 2\n")
    (repo / "backend/tests/test_new.py").write_text("def test_new():\n    assert 1\n")
    assert patch.changed_paths(patch.create(repo)) == ["backend/tests/test_new.py"]


def test_nothing_changed_gives_an_empty_patch(repo):
    assert patch.create(repo) == ""


def test_the_patch_applies_to_a_clean_checkout(repo, tmp_path_factory):
    (repo / "backend/tests/test_new.py").write_text("def test_new():\n    assert 1\n")
    text = patch.create(repo)
    clean = tmp_path_factory.mktemp("clean")
    subprocess.run(["git", "clone", "-q", str(repo), str(clean / "r")], check=True)
    patch.apply(clean / "r", text)
    assert (clean / "r/backend/tests/test_new.py").read_text() == "def test_new():\n    assert 1\n"


def test_apply_rejects_paths_outside_the_writable_area(repo):
    evil = (
        "diff --git a/backend/app/x.py b/backend/app/x.py\n--- a/backend/app/x.py\n+++ b/backend/app/x.py\n"
        "@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 99\n"
    )
    with pytest.raises(patch.PatchError, match="backend/app/x.py"):
        patch.apply(repo, evil)
    assert "return 1" in (repo / "backend/app/x.py").read_text()


def test_changed_paths_reads_renames_and_deletions():
    text = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_b.py\nsimilarity index 100%\n"
        "rename from backend/tests/test_a.py\nrename to backend/tests/test_b.py\n"
        "diff --git a/backend/tests/test_gone.py b/backend/tests/test_gone.py\ndeleted file mode 100644\n"
    )
    assert patch.changed_paths(text) == ["backend/tests/test_a.py", "backend/tests/test_b.py", "backend/tests/test_gone.py"]
