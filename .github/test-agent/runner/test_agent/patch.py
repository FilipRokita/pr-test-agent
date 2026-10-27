"""Turn the agent's working tree changes into a patch limited to writable test files, and apply it safely."""

import re
from pathlib import Path

from . import git, policy

_GLOB_SPECS = [f":(glob){spec}" for spec in policy.WRITABLE_PATHSPECS]


class PatchError(ValueError):
    pass


def create(root: Path | str) -> str:
    """Diff of new and modified writable files. Files outside the writable area never enter the patch."""
    untracked = [
        path for path in git.run(root, "ls-files", "-z", "--others", "--exclude-standard", "--", *_GLOB_SPECS).split("\0")
        if path
    ]
    if untracked:
        git.run(root, "add", "-N", "--", *[f":(literal){path}" for path in untracked])
    return git.run(root, "diff", "--binary", "--no-ext-diff", "--no-textconv", "--", *_GLOB_SPECS)


def changed_paths(patch_text: str) -> list[str]:
    paths = []
    for line in patch_text.splitlines():
        match = re.match(r"^diff --git a/(.+) b/(.+)$", line)
        if match:
            for path in dict.fromkeys(match.groups()):
                if path not in paths:
                    paths.append(path)
    return paths


def apply(root: Path | str, patch_text: str) -> None:
    """Apply a patch after checking that it only touches writable files."""
    for path in changed_paths(patch_text):
        if not policy.can_write(root, Path(root) / path):
            raise PatchError(f"patch touches a file outside the writable area: {path}")
    git.run(root, "apply", "--index", "--whitespace=nowarn", "-", stdin=patch_text)
