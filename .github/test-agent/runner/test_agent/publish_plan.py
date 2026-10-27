"""Decide what to do with the stacked pull request. Pure: no GitHub, no git."""


def decide(*, ctx: dict, agent: dict | None, verification: dict | None, stacked: dict | None,
           tip_is_bot: bool | None) -> dict:
    """`stacked` is the open stacked pull request or None; `tip_is_bot` is None when the branch does not exist."""
    if not ctx.get("should_run") or agent is None or agent.get("status") != "ok" or verification is None:
        return {"action": "keep"}
    status = verification.get("status")
    if status == "error":
        return {"action": "keep"}

    if status == "verified" and verification.get("patch_files"):
        if tip_is_bot is False:
            return {"action": "blocked", "note": "The test branch has commits from a human, so the new proposal was not pushed."}
        return {"action": "update" if stacked else "create"}

    if not stacked:
        return {"action": "keep"}
    if status == "verified":
        return {"action": "close", "reason": "This proposal is no longer needed: the current state of the pull request needs no new tests."}
    return {"action": "close", "reason": "This proposal is superseded: the latest run did not pass verification."}
