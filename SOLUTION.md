# Solution: an agent that proposes unit tests for pull requests

A pull request from this repository triggers an agent that decides whether unit tests are needed, writes or
updates them with reusable skills, runs them in a sandbox, and shows the verified result on the pull request. The
same agent was used to fill the missing tests of the existing application (backend 42% to 100%, frontend lines
48% to 100%).

## Highlights

- **Results come from runs, not from the model.** A baseline, three shuffled runs, changed-line coverage, a type and
  format check and a secret scan produce every number in the comment.
- **New tests must detect the change.** They are also run against the old source; the ones that still pass are
  listed as weak.
- **A regression is reported, not hidden.** On a pull request that claims "no behaviour change" but changes
  behaviour, the bot reports the broken test and a suspected bug and writes no test that would cover it up.
- **The model never holds the write token.** Four jobs with split privileges; tests run with no network, no
  environment and a read-only workspace.
- **Measured, not claimed.** Seven evaluation scenarios, three runs each, all passed; twelve bugs found on real runs
  are recorded and fixed.
- **The same agent filled the gaps of the application:** backend 42% to 100%, frontend lines 48% to 100%.

## 1. Main technical decisions

| Decision | Choice | Why |
|---|---|---|
| Agent platform | Claude Agent SDK (Python) with a Claude Code plugin | Policy is enforced in code before a tool runs; the model gets one test-running tool instead of a shell; structured output; an event stream to audit. |
| How results are delivered | A stacked pull request into the branch of the original one, plus one comment edited in place | No race with the author's pushes, a human decides what to merge, and CI runs on it. |
| Who holds what | Four jobs: `context` (read), `generate` (model credential), `verify` (nothing), `publish` (write token) | The model never holds the write token; the job that writes never runs the tests. |
| Where tests run | Unprivileged user, empty environment, no network, read-only workspace, no access to `.git` | Model-written code must not reach the credential or the repository. |
| What "verified" means | A baseline run, then three runs in random order, a verdict per test, type check and Prettier check, changed-line coverage, a secret scan, and the new tests run against the old source | Numbers come from deterministic steps, never from the model. |
| Coverage metric | Coverage of the lines the pull request changed | Total coverage hides an update that tests nothing. |
| Status of the bot | Advisory; the ordinary CI is the merge gate | A model outage must not block merging. |
| Skills | The open Agent Skills format, five skills | Reusable across the pull request workflow, the backfill, the evaluations and local use. |

More on the options that were compared: [design process](docs/test-agent/design-process.md).

## 2. Running the workflow and prerequisites

The workflow `.github/workflows/test-agent.yml` runs by itself on pull requests opened from this repository
(not from forks, not drafts).

Prerequisites:

1. A secret `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`, uses a Claude subscription) or
   `ANTHROPIC_API_KEY`, in the GitHub Environment `test-agent`.
2. Settings, Actions, General: "Allow GitHub Actions to create and approve pull requests".
3. Optional: the repository variable `TEST_AGENT_MODEL` (default `claude-opus-5-5`).

CI on the pull request the bot opens starts after one approval click ("Approve workflows to run"), because GitHub
holds runs started by the workflow token. Evaluators cannot trigger the workflow from a fork (forks get no
secrets), so the example below links to real runs instead.

Locally (from the repository root, after `pip install -r .github/test-agent/runner/requirements-dev.txt`):

```sh
python -m test_agent backfill --stack backend      # fill coverage gaps of one stack
python -m test_agent eval --scenario E1 --repeat 3 # run evaluation scenarios
```

Both need `PYTHONPATH=.github/test-agent/runner`; the runner tests are described in the README.

## 3. Where the agent and skills are, and how they are used

```
.github/test-agent/plugin/   the agent (agents/test-engineer.md) and five skills (skills/*/SKILL.md)
.github/test-agent/runner/   the Python runner: sandbox, tools, verification, delivery, backfill, evals
.github/test-agent/evals/    seven evaluation scenarios
.github/workflows/test-agent.yml, test-agent-evals.yml, ci.yml
```

In a run the agent follows one workflow and loads one skill per job:

| Step | Skill |
|---|---|
| Decide per changed source file: add, update or skip, with a reason | `analyze-changes` |
| Run the existing tests for a baseline | (tool `run_tests`) |
| A test fails before the agent has written anything | `triage-failing-tests`: intended change (update the test) or regression (report it, leave the test) |
| Write backend tests | `write-backend-tests` (conventions, fixtures, worked examples) |
| Write frontend tests | `write-frontend-tests` |
| Final self-review of every test | `review-test-quality` |

The skills actually invoked are read from the event stream of the run and shown in the comment, not taken from the
model's own account. How the pieces fit: [architecture](docs/test-agent/architecture.md).

## 4. Example run

[Pull request #17](https://github.com/FilipRokita/pr-test-agent/pull/17) adds a statistics feature on both
stacks: a backend endpoint, a frontend API call, hook and panel, and cache refresh after a task changes. The bot's
comment shows:

- **Result:** "5 added, 3 updated, all verified". The agent decided per file: `add` for the new repository method,
  route, API call, hook and panel; `update` for the three mutation hooks whose existing tests now also check the new
  cache refresh; `skip` for the type-only and excluded files, each with a reason.
- **Skills invoked:** `analyze-changes`, `write-backend-tests`, `write-frontend-tests`, `review-test-quality`.
  43 turns, 136 s.
- **Verification:** three shuffled runs of the whole suite (backend 63 tests, frontend 88), changed-line coverage
  100% on both stacks, and 12 of 12 new tests fail when the pull request's source changes are removed.
- The tests are in the stacked [pull request #39](https://github.com/FilipRokita/pr-test-agent/pull/39), where CI
  is green.

Other behaviours, each on a real pull request: [#19](https://github.com/FilipRokita/pr-test-agent/pull/19) is
titled "refactor, no behaviour change" but changes behaviour; the bot reports that it breaks an existing test and
a suspected bug, and proposes no test that would hide it. [#18](https://github.com/FilipRokita/pr-test-agent/pull/18)
changes behaviour on purpose; the bot updates the outdated test, in the stacked
[pull request #38](https://github.com/FilipRokita/pr-test-agent/pull/38). [#20](https://github.com/FilipRokita/pr-test-agent/pull/20)
only changes the README; the bot posts a "Skipped" comment and never calls the model.

## Evaluation

Seven fixed scenarios, three runs each, with deterministic assertions: all pass 3 of 3 (new feature, intended
change, regression, documentation only, refactor, prompt injection, frontend only). Details and the bugs the
measurements found: [tuning history](docs/test-agent/tuning-history.md).

## 5. Assumptions

- Pull requests come from people with write access to this repository; forks are not served.
- Only unit tests are in scope: no database, no network, no end-to-end tests.
- Application code is never changed by the bot; a suspected bug is reported, not fixed.
- A Claude subscription token is acceptable for this repository; production would use an API key with a limit. Every
  run shown here used a subscription token. The workflow also accepts `ANTHROPIC_API_KEY` through the same SDK, but
  that path was not exercised.

## 6. Limitations

- The sandbox is lighter than a container or a microVM: it shares the runner's kernel.
- The runner code of the `context`, `generate` and `verify` jobs comes from the pull request itself, which is
  acceptable only for trusted authors.
- The model credential is in the environment of the process that runs the agent; tests run in a child process
  without it.
- "New tests that fail without the change" shows that tests depend on the change. It is not mutation testing and
  is trivially true for tests of brand-new files.
- Quality depends on the model. Seven scenarios times three runs show that the behaviours exist; they do not
  measure how often a rare failure occurs.
- Frontend coverage is reported in lines (100%); statements are 98.8% and branches 88.3%.
- Costs shown are nominal (they are not what a subscription is billed).

More: [threat model](docs/test-agent/threat-model.md).

## 7. What to change for production

- An egress firewall and an API proxy, so the model credential never enters the job.
- A GitHub App identity for the bot instead of the workflow token.
- A container or microVM for the sandbox, and the runner always taken from the base branch.
- Mutation testing of the changed lines (for example Stryker for the frontend).
- Cost tracking per pull request and the evaluation scenarios as a gate on every prompt or skill change.
- One configuration for many repositories.

## Beyond the brief

- [Architecture](docs/test-agent/architecture.md): job flow, what the agent can do, module map (diagrams).
- [Threat model](docs/test-agent/threat-model.md): attacks, controls and the tests that exercise them.
- [Engineering practices](docs/test-agent/engineering-practices.md): pinned actions, least privilege, workflow lint, secret scanning, Dependabot, test-first runner, sandbox escape tests in CI.
- [Design process](docs/test-agent/design-process.md) and [tuning history](docs/test-agent/tuning-history.md): what was compared, measured and fixed.
