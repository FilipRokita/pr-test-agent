# General Coding Principles

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

# Project Rules

## 1. Language

Reply in the language the prompt is written in. Everything committed to the
repo, whether code, comments, commit messages, README or docs, is in English.

## 2. Answers

Lead with the answer, and keep it short. Recommend one path once a choice is
clear; enumerate alternatives only in the case "Think Before Coding" describes. If
you are not sure of a version, flag or API, verify it against the installed
tooling or the official docs before stating it.

Before a big or expensive step (subagents, long runs, large builds), say what it
is and ask.

Break it up. Short paragraphs, lists, tables. One idea per line. Never a wall of
text to wade through.

## 3. Copy

Never use an em dash in user-facing text (UI labels, headings, landing copy,
error messages, emails), README.md, or docs. End the sentence and start a new
one, or use a comma or colon. Anywhere else is fine.

## 4. Documentation

[`README.md`](README.md) (overview, stack, architecture principles) and
[`docs/`](docs/) are **not** loaded automatically: read the README when you need
the overview or before touching architecture, and read the relevant docs before
acting there. Keep both current.

Whichever one a change makes stale, update it in the same change rather than
later. When a change touches something the docs describe, update them. Add a new
doc only when it is genuinely needed (keep docs lean). This file is part of that rule too: when a workflow, command, path
or rule it names changes, update `AGENTS.md` in the same change.

## 5. Agent neutrality

Keep the repo usable by any coding agent. When there is an agent-specific
pattern and an agent-neutral standard for the same thing, use the standard.
For example, instructions live in `AGENTS.md`, not `CLAUDE.md` or `GEMINI.md`.
Add agent-specific files or config only when no neutral option exists.

## 6. Secrets

Treat the repository and its entire history as public. Before every commit:

- Never commit `.env`, keys, tokens, connection strings
  with credentials, or personal settings files. Only `.env.example` files with
  placeholders belong in git.
- Check `git status` and `git diff` first. Never run a blind `git add -A`.
- Do not put secret values in code, docs, tests, logs, commit messages, or chat. To check one, look at its length or a status code, never print it.
- Keep personal files ignored: `plans/`, `dev-only/`.
- If a secret ever leaks, rotate it first. Removing it from git does not undo
  the exposure.

## 7. Dev only

`dev-only/` is a gitignored scratch space for prototypes, mocks and experiments.
Nothing in it is part of the product.

## 8. Planning

Plans live in `plans/`, gitignored and local to one machine. One plan is
one entry: a single `.md` when that's all it needs, a folder (`plan.md` plus its
attachments) when it produces a mock, research or anything else. Name it for the
work it does, `invite-expiry` rather than `implementation-plan`, so the next plan
gets its own entry instead of overwriting this one.

Planning is not building: do not write finished code while planning unless asked.
Questions about a plan are conversation, not orders: start executing a plan only
on an explicit "start". A prototype is a guide, not a law: fix
flaws as you build and note them in the commit, and ask before changing the product's direction.

A plan is exact and backed by analysis and research. Do not guess: what you do not
know, you check in the code, the installed tooling or the official docs. Ask the
user only when the answer would change the product's or a feature's direction, or
cannot be found in the code or on the internet. A plan follows the engineering
standards in rule 10.

Whatever a plan produces stays in its entry. `dev-only/` is scratch space for
prototypes tied to no plan.

Every plan ends with a review and testing stage: check that it was fully
implemented, that every rule and acceptance criterion has code and tests, and
that the app still works as a whole. Fix what is broken or write it down as a
named limitation.

## 9. Commits

The author of every commit is the user who runs the agent. Never add the agent
as author or co-author: no `Co-Authored-By` trailer and no "Generated with"
line, in commits or in pull request descriptions.

## 10. Engineering standards

All work, not only plans, follows industry standards and best practices: DRY,
SOLID, KISS, YAGNI, clean code, separation of concerns, least privilege and other
security practices, testability, accessibility and performance, etc. The list is
examples, not a limit. Check the code, the installed tooling or the official docs
rather than guessing, and ask the user only when the answer would change the
product's direction or cannot be found.