# Engineering practices

What was done around the agent to keep the repository safe and maintainable, and where to see it.

| Practice | Where |
|---|---|
| CI as the merge gate: backend tests with a coverage floor, frontend typecheck, Prettier and tests with a coverage floor, runner tests, workflow lint, secret scan | `.github/workflows/ci.yml` |
| Every action pinned to a commit SHA with the version in a comment; tools downloaded with a checked SHA-256 | `ci.yml`, `test-agent.yml`, `scripts/install_gitleaks.sh` |
| Least privilege: `permissions: {}` for the workflow and a minimal set per job; the model credential only in the step that runs the agent; the write token only in `publish` and `cleanup` | `test-agent.yml` |
| Workflow static analysis: actionlint and zizmor on every pull request | `ci.yml` (job `workflow-lint`) |
| Secret scanning: gitleaks over the whole history on every pull request, and on every file the agent proposes | `ci.yml` (job `secret-scan`), `runner/test_agent/secrets.py` |
| Dependency updates: Dependabot for GitHub Actions, pip and npm, grouped weekly | `.github/dependabot.yml` |
| Reproducible installs: `npm ci --ignore-scripts`, pinned Python requirements | workflows, `runner/requirements.txt` |
| Concurrency and timeouts: one run per pull request, older runs cancelled, a timeout on every job | `test-agent.yml` |
| Line endings fixed to LF | `.gitattributes` |
| Security policy | `SECURITY.md`, [threat model](threat-model.md) |

## How the runner itself was built

- Rules are pure modules (`policy`, `guard`, `context`, `verdict`, `publish_plan`, `report`, `schema`, `results`)
  written test first, with the decision logic tested on scripted inputs.
- Side effects are thin adapters (`sandbox`, `git`, `github`, `agent`, `tools`) covered by integration tests that
  use a real sandbox, real git repositories and a local bare remote.
- The agent wiring is tested against a scripted fake of the model API (`tests/fake_api.py`,
  `tests/test_harness.py`): the plugin loads, only the expected tools exist, hooks deny out-of-policy calls,
  skills are read from the event stream, structured output comes back. It needs no secret and costs nothing.
- Sandbox escape attempts are tests, and they run in CI on a GitHub-hosted runner: write to the workspace, read
  `.git`, read another process's environment, open a socket, leave a process behind.
- The agent is measured, not trusted: seven [evaluation scenarios](../.github/test-agent/evals/scenarios) with
  deterministic expectations run several times each (`python -m test_agent eval`, or the manual workflow
  `test-agent-evals.yml`).
- Each bug found by a real run became a failing test first: see [tuning history](tuning-history.md).
