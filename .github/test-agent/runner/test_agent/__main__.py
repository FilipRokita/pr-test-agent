"""Command line entry point: `python -m test_agent <command>`.

context  classify the pull request and decide whether to run the agent
generate run the agent (the only command that sees the LLM credential)
patch    turn the agent's working tree changes into a patch (no credential)
verify   apply the patch and run the tests in the sandbox (no credential)
restore  put the previous proposal back in the working tree (read-only token)
publish  push the proposal, open or update the stacked pull request, write the comment (the only write token)
backfill add missing tests to the existing code of one stack (a local run of the same agent and checks)
eval     run the evaluation scenarios against the agent (each several times) and print a results table
cleanup  a pull request was closed: close its stacked pull request and delete the test branch
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from . import agent, backfill, context, evals, git, github, patch, publish, report, restore, sandbox, schema, tools, verify


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
    ctx = context.from_git(args.root, base=base, head=head, title=pull.get("title") or "", body=pull.get("body") or "")
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


def cmd_backfill(args) -> int:
    stack = args.stack
    head = git.run(args.root, "rev-parse", "HEAD").strip()
    work = Path(tempfile.mkdtemp(prefix=f"backfill-{stack}-"))
    sandbox.make_traversable(work)
    with backfill.worktree(args.root, work / "agent-tree") as tree:
        baseline = tools.run_stack(tree, stack, [], coverage=True, out_dir=sandbox.prepare_out_dir(work / "baseline"))
        if baseline.get("counts") is None:
            print(f"the baseline run produced no report: {baseline.get('error')}", file=sys.stderr)
            return 2
        if stack == "backend":
            raw = sandbox.read_output(work / "baseline", "coverage.json")
            gaps, before = backfill.backend_gaps(raw), backfill.backend_total(raw)
        else:
            raw = sandbox.read_output(work / "baseline" / "cov", "lcov.info")
            gaps, before = backfill.frontend_gaps(raw), backfill.frontend_total(raw)
        gaps = backfill.select(gaps, args.files.split(",") if args.files else None)
        print(f"{stack}: coverage {before}%, {len(gaps)} files with gaps")
        ctx = backfill.make_context(stack, gaps, head)
        reuse = args.reuse and (args.artifacts / "agent.patch").exists() and (args.artifacts / "agent-result.json").exists()
        if reuse:
            result, patch_text = _read(args.artifacts / "agent-result.json"), (args.artifacts / "agent.patch").read_text()
            print("reusing the agent result and patch found in the artifacts directory")
        else:
            model = args.model or os.environ.get("TEST_AGENT_MODEL") or "claude-opus-5-5"
            result = asyncio.run(agent.run_agent(tree, backfill.render_task(stack, gaps), model=model,
                                                 max_turns=args.max_turns, max_budget_usd=args.budget))
            if result["structured_output"] is not None:
                result["structured_output"] = schema.normalise(result["structured_output"], [g["path"] for g in gaps])
            patch_text = patch.create(tree)
    if not reuse:
        _write(args.artifacts / "agent-result.json", result)
        _write(args.artifacts / "agent.patch", patch_text)
    print(f"agent status={result['status']} turns={result['turns']} cost={result['cost_usd']} skills={result['skills_used']}")
    if result["status"] != "ok":
        return 1

    with backfill.worktree(args.root, work / "verify-tree") as tree:
        verification = verify.verify(tree, ctx, patch_text, measure=backfill.measure, out_root=work / "verify-out")
    _write(args.artifacts / "verification.json", verification)
    stack_result = verification["stacks"].get(stack, {})
    after = (stack_result.get("coverage") or {}).get("percent")
    print(f"verification status={verification['status']} files={verification['patch_files']} coverage {before}% -> {after}%")
    if verification["status"] == "verified" and after is not None:
        _write(args.artifacts / "backfill-report.md", backfill.report_markdown(
            stack, before=before, after=after, agent=result, result=result["structured_output"], verification=verification))
    return 0 if verification["status"] == "verified" else 1


def cmd_eval(args) -> int:
    directory = Path(__file__).resolve().parents[2] / "evals" / "scenarios"
    wanted = [w for w in (args.scenario or "").split(",") if w]
    folders = sorted(p for p in directory.iterdir() if p.is_dir() and (not wanted or any(p.name.startswith(w) for w in wanted)))
    model = args.model or os.environ.get("TEST_AGENT_MODEL") or "claude-opus-5-5"
    rows = []
    for folder in folders:
        scenario = evals.load(folder)
        results, cost, turns = [], 0.0, 0
        for attempt in range(1, args.repeat + 1):
            work = Path(tempfile.mkdtemp(prefix=f"eval-{scenario['id']}-"))
            sandbox.make_traversable(work)
            try:
                outcome = evals.execute(args.root, scenario, work=work, model=model, max_turns=args.max_turns, budget=args.budget)
            except Exception as error:  # an infrastructure failure is a failed attempt, not a crash of the whole run
                outcome, failures = None, [f"the run crashed: {type(error).__name__}: {str(error)[:200]}"]
            else:
                failures = evals.check(scenario["expect"], outcome)
                result = outcome.get("agent") or {}
                cost += result.get("cost_usd") or 0.0
                turns += result.get("turns") or 0
            finally:
                sandbox.remove_tree(work)
            results.append(failures)
            if failures:  # keep what the agent did, so a failing scenario can be diagnosed
                _write(args.artifacts / f"failure-{scenario['id']}-{attempt}.json", {"failures": failures, "outcome": outcome})
            print(f"{scenario['id']} attempt {attempt}: {'passed' if not failures else 'FAILED: ' + '; '.join(failures)}", flush=True)
        rows.append({"name": scenario["name"], "results": results, "cost": cost, "turns": round(turns / max(len(results), 1))})
    table = evals.summary(rows)
    _write(args.artifacts / "eval-results.json", rows)
    _write(args.artifacts / "eval-summary.md", table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as handle:
            handle.write("## Test agent evaluation\n\n" + table)
    print(table)
    return 0 if all(not failures for row in rows for failures in row["results"]) else 1


COMMANDS = {"context": cmd_context, "restore": cmd_restore, "generate": cmd_generate, "patch": cmd_patch,
            "verify": cmd_verify, "publish": cmd_publish, "cleanup": cmd_cleanup, "backfill": cmd_backfill, "eval": cmd_eval}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="test_agent", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository checkout")
    parser.add_argument("--artifacts", type=Path, default=Path("test-agent-artifacts"),
                        help="directory for the files passed between jobs")
    parser.add_argument("--scenario", help="eval: comma separated scenario ids or name prefixes (default all)")
    parser.add_argument("--repeat", type=int, default=3, help="eval: how many times each scenario runs")
    parser.add_argument("--stack", choices=["backend", "frontend"], help="backfill: the stack to work on")
    parser.add_argument("--files", help="backfill: comma separated repository paths to limit the work to")
    parser.add_argument("--model", help="backfill: model id (default TEST_AGENT_MODEL or claude-opus-5-5)")
    parser.add_argument("--reuse", action="store_true", help="backfill: verify the patch already in --artifacts instead of running the agent")
    parser.add_argument("--max-turns", type=int, default=150)
    parser.add_argument("--budget", type=float, default=15.0, help="backfill: spending limit in USD for the agent run")
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    args.artifacts = args.artifacts.resolve()
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
