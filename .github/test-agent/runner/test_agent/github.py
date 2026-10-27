"""The few GitHub operations the runner needs, through the `gh` CLI (GH_TOKEN comes from the environment)."""

import json
import subprocess

from . import report

BOT = "github-actions[bot]"


def _gh(args: list[str], body: str | None = None) -> str:
    proc = subprocess.run(["gh", *args], input=body, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {proc.stderr.strip()}")
    return proc.stdout


def upsert_comment(repo: str, pr: int, body: str, run=_gh) -> None:
    """Create the bot's comment, or edit the one it wrote earlier. Only the bot's own comments are edited."""
    pages = json.loads(run(["api", "--paginate", "--slurp", f"repos/{repo}/issues/{pr}/comments"]) or "[]")
    listing = [comment for page in pages for comment in page]
    existing = next((c for c in listing if c["user"]["login"] == BOT and report.MARKER in c["body"]), None)
    payload = json.dumps({"body": body})
    if existing:
        run(["api", "--method", "PATCH", f"repos/{repo}/issues/comments/{existing['id']}", "--input", "-"], payload)
    else:
        run(["api", "--method", "POST", f"repos/{repo}/issues/{pr}/comments", "--input", "-"], payload)
