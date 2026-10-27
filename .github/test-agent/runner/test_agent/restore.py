"""Start from the previous proposal, so that a new push updates tests instead of writing them from scratch."""

import json
from pathlib import Path

from . import git, github, patch, proposal


def restore(root: Path | str, repo: str, pr: int, run=github._gh) -> str:
    branch = f"test-agent/pr-{pr}"
    try:
        info = json.loads(run(["api", f"repos/{repo}/branches/{branch}"]))
    except RuntimeError as error:
        if "404" in str(error) or "Not Found" in str(error):
            return "nothing to restore"
        raise
    author = (info["commit"]["commit"].get("author") or {}).get("email", "")
    if not proposal.is_bot_email(author):
        return "not restored: the branch has human commits"
    diff = run(["api", "-H", "Accept: application/vnd.github.diff", f"repos/{repo}/commits/{info['commit']['sha']}"])
    try:
        patch.apply(root, diff)
    except (patch.PatchError, git.GitError) as error:
        return f"not restored: {str(error)[:160]}"
    return "restored"
