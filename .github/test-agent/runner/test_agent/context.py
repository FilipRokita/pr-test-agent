"""Turn a pull request into the agent's input: classify changed files, decide whether to run, build the task."""

import json
import re

from . import git

MAX_TITLE = 200
MAX_BODY = 4000
MAX_DIFF = 60000
_TRUNCATED = "\n[truncated]"

_BACKEND_EXCLUDED_NAMES = {"__init__.py", "main.py", "schemas.py", "models.py", "types.py", "constants.py"}
_FRONTEND_EXCLUDED_NAMES = {"types.ts", "index.ts", "constants.ts", "constants.tsx", "queryKeys.ts", "queryClient.ts"}
_FRONTEND_EXCLUDED_PATHS = {"frontend/src/main.tsx"}
_TAG_CLOSERS = re.compile(r"</(pr_metadata|diff|task|changed_files|coverage_gaps)", re.IGNORECASE)


def classify(path: str) -> dict:
    """Return stack, kind (source, test, support, other) and whether the coverage config excludes the file."""
    name = path.rsplit("/", 1)[-1]
    info = {"path": path, "stack": None, "kind": "other", "coverage_excluded": False}

    if path.startswith("backend/app/") and name.endswith(".py"):
        info.update(stack="backend", kind="source", coverage_excluded=name in _BACKEND_EXCLUDED_NAMES)
    elif path.startswith("backend/tests/"):
        info["stack"] = "backend"
        if name.startswith("test_") and name.endswith(".py") or name == "__init__.py":
            info["kind"] = "test"
        elif name.endswith(".py"):
            info["kind"] = "support"
    elif path.startswith("backend/"):
        info["stack"] = "backend"
    elif path.startswith("frontend/"):
        info["stack"] = "frontend"
        if path.startswith("frontend/src/") and re.search(r"\.tsx?$", name):
            if re.search(r"\.test\.tsx?$", name):
                info["kind"] = "test"
            elif path.startswith("frontend/src/test/") or path == "frontend/src/design-system/mocks.tsx":
                info["kind"] = "support"
            elif name.endswith(".stories.tsx"):
                info["kind"] = "other"
            else:
                info["kind"] = "source"
                info["coverage_excluded"] = (
                    path.startswith("frontend/src/design-system/")
                    or name in _FRONTEND_EXCLUDED_NAMES
                    or name.endswith(".types.ts")
                    or name.endswith(".constants.ts")
                    or path in _FRONTEND_EXCLUDED_PATHS
                )
    return info


def parse_name_status(raw: str) -> list[tuple[str, str]]:
    """Parse `git diff --name-status` output; for renames keep the new path."""
    changes = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        changes.append((parts[0][0], parts[-1]))
    return changes


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(_TRUNCATED)] + _TRUNCATED


def build_context(*, changes, title, body, base, head, diff) -> dict:
    files = []
    for status, path in changes:
        info = classify(path)
        info["status"] = status
        files.append(info)
    stacks = [s for s in ("backend", "frontend") if any(f["stack"] == s and f["kind"] == "source" and f["status"] != "D" for f in files)]
    runnable = [f for f in files if f["kind"] == "source" and f["status"] != "D"]

    if not files:
        should_run, reason = False, "no changed files"
    elif not runnable:
        should_run, reason = False, "no source files changed (documentation, tests, configuration or deletions only)"
    else:
        should_run, reason = True, ""

    return {
        "base": base,
        "head": head,
        "title": _cap(title, MAX_TITLE),
        "body": _cap(body, MAX_BODY),
        "diff": _cap(diff, MAX_DIFF),
        "files": files,
        "stacks": stacks,
        "should_run": should_run,
        "skip_reason": reason,
    }


def _defang(text: str) -> str:
    """Untrusted text must not be able to close the tag that wraps it."""
    return _TAG_CLOSERS.sub(lambda m: "<\\/" + m.group(1), text)


def render_task(ctx: dict) -> str:
    listed = [
        {"path": f["path"], "status": f["status"], "stack": f["stack"], "kind": f["kind"],
         "coverage_excluded": f["coverage_excluded"]}
        for f in ctx["files"]
    ]
    return (
        "<task>\n"
        f"Mode: pull_request. Base: {ctx['base']}. Head: {ctx['head']}.\n"
        "Add or update unit tests for the changed code, following your workflow.\n"
        "</task>\n"
        "<changed_files>\n"
        + "\n".join(json.dumps(f) for f in listed)
        + "\n</changed_files>\n"
        '<pr_metadata trust="untrusted">\n'
        f"Title: {_defang(ctx['title'])}\n"
        "Body:\n"
        f"{_defang(ctx['body'])}\n"
        "</pr_metadata>\n"
        '<diff trust="untrusted">\n'
        f"{_defang(ctx['diff'])}\n"
        "</diff>\n"
    )


def apply_previous_run(ctx: dict, changes_since_previous: list[tuple[str, str]] | None) -> dict:
    """A push that only touches tests or other files (for example merging the proposal) needs no new run."""
    if changes_since_previous is None or not ctx["should_run"]:
        return ctx
    if any(classify(path)["kind"] == "source" and status != "D" for status, path in changes_since_previous):
        return ctx
    return {**ctx, "should_run": False, "keep_previous": True,
            "skip_reason": "no new source changes since the last run"}


def from_git(root, *, base: str, head: str, title: str, body: str) -> dict:
    """The context of the change between two commits of a checkout."""
    changes = parse_name_status(git.run(root, "diff", "--name-status", "--find-renames", f"{base}...{head}"))
    sources = [path for status, path in changes if status != "D" and classify(path)["kind"] == "source"]
    diff = git.run(root, "diff", "--no-ext-diff", "--no-textconv", f"{base}...{head}", "--", *sources) if sources else ""
    return build_context(changes=changes, title=title, body=body, base=base, head=head, diff=diff)
