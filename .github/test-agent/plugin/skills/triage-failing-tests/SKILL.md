---
name: triage-failing-tests
description: Decides, for each existing test that fails on the pull request head, whether the pull request changed the behaviour on purpose (update the test) or introduced a regression (keep the test, report a finding). Use whenever the baseline run_tests call reports failures.
---

# Triage failing tests

`main` is green (CI is the merge gate), so a test that fails on the pull request head before you edit
anything fails because of the pull request.

For each failing test:

1. Name the behaviour the test asserts, in one sentence.
2. Find the change that breaks it (diff, then the full source).
3. Look for evidence of intent, strongest first:
   - the pull request title or body describes the new behaviour;
   - a docstring, comment, or error message in the change states it;
   - the change is consistent across layers (backend limit and frontend `validateTodo` changed together);
   - other tests or call sites were updated the same way.
4. Look for evidence of a regression:
   - the pull request says "refactor", "no behaviour change", or describes something else;
   - the change contradicts a rule stated elsewhere (docstring, validator, the other stack);
   - the shape of a typical slip: inverted condition, `<` vs `<=`, wrong field, off by one, missing await.
5. Decide:
   - **Intended**: update the assertion to the new behaviour, keep the test's other checks, add a boundary
     case. Decision `update`, reason cites the evidence ("PR body: title limit raised to 200").
   - **Regression**: do not touch the test. Record `suspected_bug` with the file, line, what the test
     expects, and `expected_behavior`. If you wrote a new test that exposes the regression, remove it from
     the patch and put its source in `suggested_test`.
   - **Unclear**: do not touch the test. Record `spec_mismatch` and state the question for the author.

Never delete a failing test, loosen an assertion to make it pass, or mark it skipped.
The verify job reports failures in tests you did not touch as failures caused by the pull request, so
leaving a failing test in place is the correct, visible outcome.
