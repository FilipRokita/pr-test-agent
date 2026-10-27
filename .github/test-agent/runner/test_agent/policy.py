"""Path policy shared by the agent's tool hooks and the patch guard.

One definition of "what the agent may write and read", so what is prevented while the agent runs is exactly
what is rejected afterwards.
"""

import os
import re
from pathlib import Path

# Pathspecs for `git add` / `git diff`, kept next to the regexes that enforce the same set.
WRITABLE_PATHSPECS = (
    "backend/tests/**/test_*.py",
    "backend/tests/**/__init__.py",
    "frontend/src/**/*.test.ts",
    "frontend/src/**/*.test.tsx",
)

_WRITABLE = (
    re.compile(r"^backend/tests/(?:.+/)?test_[^/]+\.py$"),
    re.compile(r"^backend/tests/(?:.+/)?__init__\.py$"),
    re.compile(r"^frontend/src/(?:.+/)?[^/]+\.test\.tsx?$"),
)
# Shared support files stay read-only: a hook in conftest.py or setup.ts could change test outcomes.
_READ_ONLY_DIRS = ("frontend/src/test/",)


def _relative(root: Path | str, path: Path | str) -> str | None:
    """Return the repository-relative POSIX path of `path`, or None if it resolves outside `root`."""
    root_real = Path(os.path.realpath(root))
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(root) / candidate
    real = Path(os.path.realpath(candidate))
    try:
        return real.relative_to(root_real).as_posix()
    except ValueError:
        return None


def can_write(root: Path | str, path: Path | str) -> bool:
    relative = _relative(root, path)
    if relative is None:
        return False
    if any(relative.startswith(prefix) for prefix in _READ_ONLY_DIRS):
        return False
    return any(pattern.match(relative) for pattern in _WRITABLE)


def can_read(root: Path | str, path: Path | str) -> bool:
    relative = _relative(root, path)
    if relative is None:
        return False
    parts = relative.split("/")
    if parts[0] == ".git":
        return False
    name = parts[-1]
    if name.startswith(".env") and name != ".env.example":
        return False
    return True


def glob_pattern_ok(pattern: str) -> bool:
    """A Glob/Grep pattern must stay relative and must not climb out of the searched directory."""
    if pattern.startswith("/"):
        return False
    return ".." not in pattern.replace("\\", "/").split("/")
