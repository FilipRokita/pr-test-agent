---
name: analyze-changes
description: Classifies files changed in a Taskly pull request and decides per source file whether unit tests must be added, updated, or skipped, with a reviewer-verifiable reason. Use at the start of every test-engineer run, before writing any test.
---

# Analyze changes

## 1. Classify

| Path | Kind | Where its tests live |
|---|---|---|
| `backend/app/**/*.py` | backend source | `backend/tests/<same subpath>/test_<module>.py` |
| `frontend/src/**/*.ts(x)`, not `*.test.*`, not `*.stories.tsx` | frontend source | same folder, `<Name>.test.ts(x)` |
| `backend/tests/**`, `frontend/src/**/*.test.*`, `frontend/src/test/**` | test (support files are read-only) | n/a |
| anything else (docs, CI, Docker, lockfiles, configs, CSS, assets) | other | skip |

Files the coverage config excludes are not test targets themselves:
backend `__init__.py`, `main.py`, `schemas.py`, `models.py`, `types.py`, `constants.py`;
frontend `src/design-system/**`, `types.ts`, `*.types.ts`, `index.ts`, `constants.*`, `queryKeys.ts`,
`queryClient.ts`, `main.tsx`.
Their changes can still change behaviour elsewhere: a `Field` limit in `schemas.py` changes API
validation, a new `Priority` value changes sorting. Grep for the changed symbol and decide for the
consumers.

## 2. Read before deciding

- Read the whole changed file, not only the diff.
- Find existing tests: the mapped path first, then Grep the test folders for the module and symbol names.
- Read those tests.

## 3. Decide

- **add**: changed or new behaviour (branch, condition, return value, error, side effect, rendered output,
  user interaction) that no existing test asserts.
- **update**: an existing test asserts behaviour the pull request changes on purpose (follow
  `triage-failing-tests`), or references a renamed or removed symbol.
- **skip**: no behaviour change (formatting, comments, types only, styling), behaviour already asserted
  (confirm with the baseline coverage of the changed lines), or not a unit-test concern. The reason must
  let a reviewer check it in under a minute.

Priority when time is short: error paths and boundaries, then the main flow, then trivial code.

## 4. Examples

- `features/todos/router.py` adds `POST /api/todos/{todo_id}/duplicate` -> add: router tests with
  `repository_mock` (201 with the copy, 404 for a missing task, 422 for `todo_id` 0) and repository tests
  for the new method.
- `TodoItem.tsx` changes only a `className` -> skip: "Styling only; no rendered text, state, or handler
  changed."
- `validators.py` starts accepting `null` for `description` and the PR body says so -> update: remove
  `description` from the parametrized null-rejection test in `test_validators.py` and add a case for the
  accepted `null`.
- `README.md` -> skip: "Documentation."
