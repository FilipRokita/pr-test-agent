import os

import pytest

from test_agent import policy


@pytest.fixture
def root(tmp_path):
    (tmp_path / "backend/tests/features").mkdir(parents=True)
    (tmp_path / "backend/app").mkdir(parents=True)
    (tmp_path / "frontend/src/test").mkdir(parents=True)
    (tmp_path / "frontend/src/features").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.mark.parametrize(
    "path",
    [
        "backend/tests/test_new.py",
        "backend/tests/features/todos/test_router.py",
        "backend/tests/features/todos/__init__.py",
        "frontend/src/features/todos/TodoList.test.tsx",
        "frontend/src/lib/http.test.ts",
    ],
)
def test_test_files_are_writable(root, path):
    assert policy.can_write(root, root / path)


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/features/todos/router.py",
        "backend/tests/conftest.py",
        "backend/tests/mocks.py",
        "backend/tests/helpers.py",
        "frontend/src/test/setup.ts",
        "frontend/src/test/todoFixture.ts",
        "frontend/src/test/extra.test.ts",
        "frontend/src/App.tsx",
        "frontend/package.json",
        "frontend/vite.config.ts",
        "backend/pyproject.toml",
        ".github/workflows/ci.yml",
        "README.md",
        ".env",
    ],
)
def test_everything_else_is_not_writable(root, path):
    assert not policy.can_write(root, root / path)


def test_paths_outside_the_repository_are_not_writable(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "backend/tests/test_x.py"
    assert not policy.can_write(root, outside)


def test_dotdot_cannot_escape_the_writable_area(root):
    assert not policy.can_write(root, root / "backend/tests/../app/x.py")
    assert not policy.can_write(root, root / "backend/tests/../../outside/test_x.py")


def test_relative_paths_resolve_against_the_root(root):
    assert policy.can_write(root, "backend/tests/test_new.py")
    assert not policy.can_write(root, "backend/app/new.py")


def test_symlink_to_a_source_file_is_not_writable(root):
    target = root / "backend/app/secret.py"
    target.write_text("x = 1\n")
    link = root / "backend/tests/test_link.py"
    os.symlink(target, link)
    assert not policy.can_write(root, link)


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/main.py",
        "backend/tests/conftest.py",
        "frontend/src/App.tsx",
        ".env.example",
        "README.md",
    ],
)
def test_repository_files_are_readable(root, path):
    assert policy.can_read(root, root / path)


@pytest.mark.parametrize(
    "path",
    [".env", ".env.local", ".env.production", ".git/config", ".git/hooks/pre-commit", "backend/.env"],
)
def test_secrets_and_git_internals_are_not_readable(root, path):
    assert not policy.can_read(root, root / path)


def test_paths_outside_the_repository_are_not_readable(root):
    assert not policy.can_read(root, "/etc/passwd")
    assert not policy.can_read(root, "/proc/self/environ")
    assert not policy.can_read(root, root / "../elsewhere.txt")


@pytest.mark.parametrize("pattern", ["/etc/*", "../secrets/*", "backend/../../x", "**/../*"])
def test_glob_patterns_that_escape_are_rejected(pattern):
    assert not policy.glob_pattern_ok(pattern)


@pytest.mark.parametrize("pattern", ["backend/tests/**/*.py", "**/*.tsx", "TodoList*", ""])
def test_ordinary_glob_patterns_are_accepted(pattern):
    assert policy.glob_pattern_ok(pattern)


def test_writable_globs_cover_exactly_the_writable_patterns():
    assert set(policy.WRITABLE_PATHSPECS) == {
        "backend/tests/**/test_*.py",
        "backend/tests/**/__init__.py",
        "frontend/src/**/*.test.ts",
        "frontend/src/**/*.test.tsx",
    }
