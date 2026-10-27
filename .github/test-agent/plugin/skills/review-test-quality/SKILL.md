---
name: review-test-quality
description: Final self-review checklist for unit tests written or changed in a test-engineer run. Use after the tests pass and before the final answer.
---

# Review test quality

Go through every test you wrote or changed. Fix, then re-run the touched files.

- [ ] **It can fail.** Flip the condition or return value the test is about in your head. If the test would
      still pass, strengthen the assertion.
- [ ] **Behaviour, not internals.** Assert outputs, responses, rendered text, and calls at boundaries.
      No private state, no assertions on how the unit calls its own helpers.
- [ ] **One behaviour per test**, and the name says which.
- [ ] **Edges covered** where the change has them: limits, empty values, null, error responses, 404.
- [ ] **Deterministic.** No real clock, network, sleeps, random data, or order dependence. Fresh
      `QueryClient` per test; mocks reset.
- [ ] **Matches the file around it**: imports, fixtures, mocks, naming, Prettier style.
- [ ] **No duplicates** of existing tests; extend a parametrize list or `it.each` table instead.
- [ ] **Nothing forbidden**: skip, xfail, `.only`, `.todo`, coverage pragmas, snapshot-only assertions,
      reads of real environment variables or secrets.
- [ ] **Decision list complete**: every changed source file has exactly one decision with a checkable
      reason.
