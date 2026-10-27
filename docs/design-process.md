# Design process

How the design was reached: what was compared, what was measured before committing to it, and what an independent
review changed.

## The problem

A pull request changes code. A bot should decide whether unit tests are needed, write or update them with an agent
that uses reusable skills, run them, and show the result on the pull request, for a FastAPI backend and a React
frontend, with the agent's output trusted no further than it can be checked.

## Platform

| Option | Verdict |
|---|---|
| Claude Agent SDK (Python) with a Claude Code plugin | **Chosen.** Policy is enforced in code before a tool runs (hooks), the model gets one custom tool instead of a shell, structured output, budget and turn limits, an event stream to audit. |
| Claude Code CLI | Same engine, but policy lives in flags and shell hooks. |
| `claude-code-action` | Convenient, but it lets the model publish; this design wants publishing to be deterministic code. |
| OpenAI Codex, GitHub Copilot coding agent, Gemini CLI | Not available for this work; Codex also reads `AGENTS.md` natively, which is a file for developers here. |
| GitHub Agentic Workflows | The best security architecture of the group; its job split was adopted by hand (read-only agent, deterministic publishing). It is new and compiles workflows, which makes a custom verification pipeline harder. |
| A framework on a raw API | Would mean rebuilding file tools and context handling. |

Skills follow the open Agent Skills format (`SKILL.md`), supported by Claude, Codex, Copilot and Gemini, so they are
portable even if the platform changes.

## What was taken from existing tools

- [Meta's TestGen-LLM](https://arxiv.org/abs/2402.09171): accept a generated test only if it builds, passes
  repeatedly and adds coverage. Here: three shuffled runs and coverage of the changed lines.
- [CodeRabbit](https://docs.coderabbit.ai/finishing-touches/unit-test-generation) and
  [Qodo Cover](https://github.com/qodo-ai/qodo-cover): deliver tests as a separate pull request. Here: a stacked
  pull request into the branch of the original one.
- [GitHub's agentic workflow design](https://github.blog/security/vulnerability-research/under-the-hood-security-architecture-of-github-agentic-workflows/):
  the agent reads, other jobs write; outputs are buffered and checked before they take effect.

## Things measured before building on them

| Question | Result |
|---|---|
| Can the agent be loaded from a plugin outside the project's own instructions? | Yes: `setting_sources=[]` keeps the repository's `AGENTS.md` and skills out of the session; the plugin's agent and skills are in the model's context (checked on the requests a scripted fake sent). |
| Can a hook stop a write outside the tests and a read outside the repository? | Yes, in every permission mode; denials are reported in the result. |
| Does a sandbox without network and secrets work on a GitHub-hosted runner, with real test suites? | Yes (`ubuntu-24.04`): unprivileged user, empty environment, no network, read-only workspace; backend and frontend suites pass with coverage. |
| Does a pull request opened or a branch pushed with the workflow token start CI? | It starts in an approval-required state; one click (or one API call) runs it. This is why the tests are delivered as a pull request: a human gate exists anyway. |
| Does a Claude subscription token work with the SDK in CI, with `claude-opus-5-5`? | Yes. |
| What does one real agent run look like? | A one-method backend change: 16 turns, 33 seconds, a parametrized test in the style of the repository's own tests. |

## Independent reviews

Two independent reviews of the plan, by a separate agent that had to find problems, changed the design:

- **Sandbox escape through the workspace** (verified by the reviewer): with a writable workspace, test code could
  plant git configuration that runs later in a process holding the credential. The workspace became read-only for
  the sandbox, `.git` unreachable, outputs go elsewhere, and every git call disables such configuration.
- **A passing result can be forged**: shared support files (`conftest.py`, `setup.ts`) became read-only, the guard
  gained more patterns (skip variants, assertion-free tests), and the set of existing test ids must not change.
- **The base branch is not a security boundary** for a pull request that can edit the workflow file itself; the
  actual boundary is who can trigger the workflow, so the design was documented that way.
- The regression scenario had no test to break, a mutation-testing step could not be scoped to a diff, and the
  skill examples gave away the answers of two scenarios; all three were changed.
- Delivery as a commit on the author's branch was replaced by a stacked pull request (no races with the author, a
  human merge decision).

Bugs found later by real runs, and how they were fixed, are in [tuning history](tuning-history.md).
