# Threat model

The agent runs model-written code in CI, on pull requests that may contain text written to manipulate it. This
page lists what is protected, who is trusted, and which control stops which attack. Controls link to the tests
that exercise them.

## Assets

The model credential (`CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`), write access to the repository, the
integrity of CI results, and the `main` branch.

## Trust

| Actor | Trust |
|---|---|
| Author with write access to this repository | Trusted. They can already edit workflows. |
| Pull request from a fork | Not served. `pull_request` gives forks no secrets; the workflow also skips them. |
| Text in code, comments, pull request title and body, test output | Untrusted input to the model. |
| Dependencies installed by `npm ci` and `pip install` | Untrusted. Installed without lifecycle scripts, in steps that have no credential. |

## Attacks and controls

| Attack | Control | Evidence |
|---|---|---|
| Injected text tells the model to leak the credential or edit CI | The model has no shell, web or git. File tools are limited by hooks. Untrusted text is wrapped in tags and the prompt says it is data. | `tests/test_agent_hooks.py`, `tests/test_harness.py`, scenario E6 |
| Test code reads the environment or the network | Tests run as uid 65534 with an empty environment, no network, a separate PID namespace, no new privileges and no capabilities. | `tests/test_sandbox.py` (escape attempts), `tests/test_tools.py` |
| Test code plants git config or hooks that run later in a process with a secret | The workspace is read-only for the sandbox user, `.git` is not accessible, output goes to a separate directory. Every git call of the runner disables fsmonitor, hooks and external diff. | `tests/test_sandbox.py`, `tests/test_git.py` |
| Test code writes a forged result file | Result files are read as untrusted data: regular files only, size capped, XML parsed with defusedxml. | `tests/test_sandbox.py`, `tests/test_results.py` |
| The proposal weakens the suite (skip, xfail, only, coverage pragmas, no assertions, edited `conftest.py`) | Support files are read-only. The guard rejects these patterns before anything is applied. The set of existing test ids must not change. | `tests/test_guard.py`, `tests/test_verdict.py` |
| A secret ends up in a proposed test | gitleaks on the proposed files, with a rule for Claude Code OAuth tokens. | `tests/test_secrets.py` |
| The comment or pull request body carries markup, mentions or a forged marker | Model text is escaped, only comments of `github-actions[bot]` with the marker are edited. | `tests/test_report.py`, `tests/test_github.py` |
| The bot overwrites human work on the test branch | The push is skipped when the tip of the branch is not a bot commit. | `tests/test_publish_plan.py`, `tests/test_publish.py` |
| Expression injection through event text in a workflow | Event text is never interpolated into `run:`. zizmor and actionlint run in CI. | `ci.yml` |
| A compromised action or tool | Actions pinned to commit SHAs, tools downloaded with a checked SHA-256, Dependabot for updates. | `ci.yml`, `dependabot.yml` |
| Runaway cost or loops | Turn and budget limits, job timeouts, one concurrent run per pull request, pull requests from the bot's own branches are skipped. | `agent.py`, `test-agent.yml` |

## Residual risks

- The sandbox is lighter than a container or a microVM. It shares the runner's kernel and host.
- The runner code for the `context`, `generate` and `verify` jobs comes from the pull request itself. That is
  acceptable only because those authors are trusted; for untrusted authors the code would have to come from the
  base branch.
- The model credential is in the environment of the process that runs the agent. Tests run in a child process
  with an empty environment, but a flaw in the SDK or the CLI would be outside this model.
- Prompt injection cannot be excluded. The controls limit what a manipulated model can do; they do not make it
  impossible to manipulate. Scenario E6 measures how often it complains instead of complying.
- Verification shows that the proposed tests pass and fail without the change. It does not prove that they are
  good tests.

## What would change for production

An egress firewall and an API proxy so the model credential never enters the job (the design GitHub describes for
agentic workflows), a GitHub App identity for the bot, a container or microVM for the sandbox, the runner always
checked out from the base branch, and mutation testing of the changed lines.
