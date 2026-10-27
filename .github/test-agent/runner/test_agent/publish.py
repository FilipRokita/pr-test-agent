"""Write the result of a run to GitHub: the stacked pull request with the tests, and the comment.

This is the only module that writes to GitHub. It runs in a job that has a write token and never runs the tests
of the pull request.
"""

import json
import os
import re

from . import github as gh_cli
from . import proposal, publish_plan, report

BRANCH = "test-agent/pr-{number}"
CREDENTIALS = (("credential.helper", "!gh auth git-credential"),)


class Github:
    """The GitHub operations of one repository."""

    def __init__(self, repo: str, run=gh_cli._gh):
        self.repo, self._run = repo, run

    def _api(self, *args, payload=None):
        extra = ["--input", "-"] if payload is not None else []
        out = self._run(["api", *args, *extra], json.dumps(payload) if payload is not None else None)
        return json.loads(out) if out.strip() else None

    def open_stacked(self, branch):
        owner = self.repo.split("/")[0]
        pulls = self._api(f"repos/{self.repo}/pulls?state=open&head={owner}:{branch}") or []
        return {"number": pulls[0]["number"]} if pulls else None

    def branch_tip_email(self, branch):
        try:
            data = self._api(f"repos/{self.repo}/branches/{branch}")
        except RuntimeError as error:
            if "404" in str(error) or "Not Found" in str(error):
                return None
            raise
        return (data["commit"]["commit"]["author"] or {}).get("email", "")

    def create_pr(self, *, title, head, base, body):
        return self._api(f"repos/{self.repo}/pulls", "--method", "POST",
                         payload={"title": title, "head": head, "base": base, "body": body})["number"]

    def update_pr(self, number, *, title, body):
        self._api(f"repos/{self.repo}/pulls/{number}", "--method", "PATCH", payload={"title": title, "body": body, "state": "open"})

    def close_pr(self, number, comment):
        self._api(f"repos/{self.repo}/issues/{number}/comments", "--method", "POST", payload={"body": comment})
        self._api(f"repos/{self.repo}/pulls/{number}", "--method", "PATCH", payload={"state": "closed"})

    def delete_branch(self, branch):
        try:
            self._run(["api", "--method", "DELETE", f"repos/{self.repo}/git/refs/heads/{branch}"], None)
        except RuntimeError as error:
            if "422" not in str(error) and "404" not in str(error) and "Not Found" not in str(error):
                raise

    def upsert_comment(self, pr, body):
        gh_cli.upsert_comment(self.repo, pr, body, run=self._run)


def _title(ctx: dict) -> str:
    """A pull request title is plain text: one line, no angle brackets, capped."""
    text = re.sub(r"[\s<>`]+", " ", f"Tests for #{ctx['pull_request']}: {ctx.get('title', '')}").strip()
    return text if len(text) <= 200 else text[:199] + "\u2026"


def publish(root, ctx, agent, verification, patch_text, *, gh, remote="origin", run_url="") -> dict:
    branch = BRANCH.format(number=ctx["pull_request"])
    stacked = gh.open_stacked(branch)
    email = gh.branch_tip_email(branch)
    plan = publish_plan.decide(ctx=ctx, agent=agent, verification=verification, stacked=stacked,
                               tip_is_bot=None if email is None else proposal.is_bot_email(email))
    action, number, note = plan["action"], (stacked or {}).get("number"), plan.get("note", "")

    if action in ("create", "update"):
        proposal.commit(root, ctx["head"], branch, patch_text, f"Add tests proposed by the test agent for #{ctx['pull_request']}")
        token = {key: os.environ[key] for key in ("GH_TOKEN", "GITHUB_TOKEN") if key in os.environ}
        proposal.push(root, branch, remote, extra_env=token, config=CREDENTIALS)
        body = report.render_pull_request_body(ctx, agent, verification)
        if action == "create":
            number = gh.create_pr(title=_title(ctx), head=branch, base=ctx["head_ref"], body=body)
        else:
            gh.update_pr(number, title=_title(ctx), body=body)
    elif action == "close":
        gh.close_pr(number, plan["reason"])
        number = None

    if not ctx.get("keep_previous"):
        gh.upsert_comment(ctx["pull_request"], report.render(ctx, agent, verification, run_url=run_url,
                                                            stacked=number if action != "blocked" else None, note=note))
    return {"action": action, "stacked": number, "note": note}


def cleanup(ctx, *, gh) -> None:
    """The pull request was closed: close its stacked pull request and delete the test branch."""
    branch = BRANCH.format(number=ctx["pull_request"])
    stacked = gh.open_stacked(branch)
    if stacked:
        gh.close_pr(stacked["number"], "The pull request this proposal belongs to was closed.")
    gh.delete_branch(branch)
