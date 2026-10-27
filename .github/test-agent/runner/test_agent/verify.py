"""Check a proposed patch by applying it to a clean checkout and running the tests in the sandbox.

This runs in a job that holds no secrets. The patch is data: it is checked for paths first and only then applied.
"""

from pathlib import Path

from . import git, patch, sandbox, tools


def verify(root: Path, ctx: dict, patch_text: str, *, runner=tools.run_stack, out_root: Path | None = None) -> dict:
    root = Path(root)
    if not patch_text.strip():
        return {"status": "verified", "patch_files": [], "stacks": {}}

    try:
        patch.apply(root, patch_text)
    except (patch.PatchError, git.GitError) as error:  # an unappliable patch is a rejection, not a crash
        return {"status": "rejected", "patch_files": [], "stacks": {}, "reason": str(error)}

    files = patch.changed_paths(patch_text)
    out_root = Path(out_root) if out_root else root.parent / "test-agent-out"
    stacks = {}
    for index, stack in enumerate(ctx["stacks"], start=1):
        out_dir = sandbox.prepare_out_dir(out_root / f"{stack}-{index}")
        result = runner(root, stack, [], coverage=False, out_dir=out_dir)
        stacks[stack] = {"ok": result["ok"], "counts": result.get("counts"), "error": result.get("error", "")}

    status = "verified" if all(s["ok"] for s in stacks.values()) else "failing"
    return {"status": status, "patch_files": files, "stacks": stacks}
