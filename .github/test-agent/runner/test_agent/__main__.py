"""Command line entry point: `python -m test_agent <command>`.

context  classify the pull request and decide whether to run the agent
generate run the agent (the only command that sees the LLM credential)
patch    turn the agent's working tree changes into a patch (no credential)
verify   apply the patch and run the tests in the sandbox (no credential)
restore  put the previous proposal back in the working tree (read-only token)
publish  push the proposal, open or update the stacked pull request, write the comment (the only write token)
cleanup  a pull request was closed: close its stacked pull request and delete the test branch
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from . import agent, context, git, github, patch, publish, report, restore, schema, verify


def _read(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, indent=2) + "\n")


def _set_output(name: str, value: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a") as handle:
            handle.write(f"{name}={value}\n")


def _event() -> dict:
    with open(os.environ["GITHUB_EVENT_PATH"]) as handle:
        return json.load(handle)


def cmd_context(args) -> int:
    pull = _event()["pull_request"]
    base, head = pull["base"]["sha"], pull["head"]["sha"]
    changes = context.parse_name_status(
        git.run(args.root, "diff", "--name-status", "--find-renames", f"{base}...{head}"))
    sources = [p for s, p in changes if s != "D" and context.classify(p)["kind"] == "source"]
    diff = git.run(args.root, "diff", "--no-ext-diff", "--no-textconv", f"{base}...{head}", "--", *sources) if sources else ""
    ctx = context.build_context(changes=changes, title=pull.get("title") or "", body=pull.get("body") or "",
                                base=base, head=head, diff=diff)
    ctx["pull_request"] = pull["number"]
    ctx["head_ref"] = pull["head"]["ref"]
    repository = os.environ.get("GITHUB_REPOSITORY")
    if ctx["should_run"] and repository and os.environ.get("GH_TOKEN"):
        body = github.bot_comment_body(repository, pull["number"])
        previous = report.previous_head(body) if body else None
        if previous and git.run(args.root, "rev-parse", "--verify", "--quiet", f"{previous}^{{commit}}", check=False).strip():
            since = context.parse_name_status(
                git.run(args.root, "diff", "--name-status", "--find-renames", previous, head))
            ctx = context.apply_previous_run(ctx, since)
    _write(args.artifacts / "context.json", ctx)
    _set_output("should_run", "true" if ctx["should_run"] else "false")
    print(f"should_run={ctx['should_run']} stacks={ctx['stacks']} {ctx['skip_reason']}")
    return 0


def cmd_restore(args) -> int:
    ctx = _read(args.artifacts / "context.json")
    if not ctx or not ctx["should_run"]:
        return 0
    status = restore.restore(args.root, os.environ["GITHUB_REPOSITORY"], ctx["pull_request"])
    print(f"previous proposal: {status}")
    return 0


def cmd_generate(args) -> int:
    ctx = _read(args.artifacts / "context.json")
    if not ctx or not ctx["should_run"]:
        return 0
    for name in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        if not os.environ.get(name):
            os.environ.pop(name, None)  # an empty secret must not be mistaken for a credential
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")):
        _write(args.artifacts / "agent-result.json", {"status": "skipped_no_credentials"})
        print("no LLM credentials configured; skipping")
        return 0

    model = os.environ.get("TEST_AGENT_MODEL") or "claude-opus-5-5"
    result = asyncio.run(agent.run_agent(args.root, context.render_task(ctx), model=model))
    if result["structured_output"] is not None:
        sources = [f["path"] for f in ctx["files"] if f["kind"] == "source" and f["status"] != "D"]
        result["structured_output"] = schema.normalise(result["structured_output"], sources)
    _write(args.artifacts / "agent-result.json", result)
    print(f"agent status={result['status']} turns={result['turns']} skills={result['skills_used']}")
    return 0 if result["status"] == "ok" else 1


def cmd_patch(args) -> int:
    _write(args.artifacts / "agent.patch", patch.create(args.root))
    return 0


def cmd_verify(args) -> int:
    ctx = _read(args.artifacts / "context.json")
    patch_path = args.artifacts / "agent.patch"
    patch_text = patch_path.read_text() if patch_path.exists() else ""
    result = verify.verify(args.root, ctx, patch_text, out_root=Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "test-agent-out")
    _write(args.artifacts / "verification.json", result)
    print(f"verification status={result['status']} files={result['patch_files']}")
    return 0


def cmd_publish(args) -> int:
    ctx = _read(args.artifacts / "context.json")
    run_url = "/".join([os.environ.get("GITHUB_SERVER_URL", ""), os.environ.get("GITHUB_REPOSITORY", ""),
                        "actions/runs", os.environ.get("GITHUB_RUN_ID", "")])
    patch_path = args.artifacts / "agent.patch"
    result = publish.publish(
        args.root, ctx, _read(args.artifacts / "agent-result.json"), _read(args.artifacts / "verification.json"),
        patch_path.read_text() if patch_path.exists() else "",
        gh=publish.Github(os.environ["GITHUB_REPOSITORY"]), run_url=run_url)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as handle:
            handle.write(f"Test agent: {result['action']}" + (f", stacked pull request #{result['stacked']}" if result["stacked"] else "") + "\n")
    print(f"publish: {result}")
    return 0


def cmd_cleanup(args) -> int:
    publish.cleanup({"pull_request": _event()["pull_request"]["number"]},
                    gh=publish.Github(os.environ["GITHUB_REPOSITORY"]))
    return 0


COMMANDS = {"context": cmd_context, "restore": cmd_restore, "generate": cmd_generate, "patch": cmd_patch,
            "verify": cmd_verify, "publish": cmd_publish, "cleanup": cmd_cleanup}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="test_agent", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository checkout")
    parser.add_argument("--artifacts", type=Path, default=Path("test-agent-artifacts"),
                        help="directory for the files passed between jobs")
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    args.artifacts = args.artifacts.resolve()
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
