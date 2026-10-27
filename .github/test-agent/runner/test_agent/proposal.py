"""Turn a verified patch into one bot commit on the head of the pull request, and push it."""

from pathlib import Path

from . import git, patch

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def is_bot_email(email: str) -> bool:
    return email == BOT_EMAIL


def commit(root: Path | str, head_sha: str, branch: str, patch_text: str, message: str) -> str:
    """Create `branch` at `head_sha` with a single commit holding the patch. The patch is path-checked first."""
    git.run(root, "checkout", "-q", "-B", branch, head_sha)
    patch.apply(root, patch_text)
    files = patch.changed_paths(patch_text)
    git.run(root, "add", "--", *[f":(literal){path}" for path in files])
    git.run(root, "commit", "-q", "-m", message,
            config=(("user.name", BOT_NAME), ("user.email", BOT_EMAIL)))
    return git.run(root, "rev-parse", "HEAD").strip()


def push(root: Path | str, branch: str, remote: str = "origin", extra_env: dict | None = None,
         config: tuple[tuple[str, str], ...] = ()) -> None:
    git.run(root, "push", "--force", remote, f"{branch}:refs/heads/{branch}", extra_env=extra_env, config=config)
