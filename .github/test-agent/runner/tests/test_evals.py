import pytest

from test_agent import evals

DECISION = {"file": "backend/app/x.py", "action": "add", "reason": "r", "test_files": ["backend/tests/test_x.py"]}
PATCH = "diff --git a/backend/tests/test_x.py b/backend/tests/test_x.py\nnew file mode 100644\n--- /dev/null\n+++ b/backend/tests/test_x.py\n@@ -0,0 +1 @@\n+def test_x():\n"


def outcome(**over):
    base = {
        "ctx": {"should_run": True},
        "agent": {"status": "ok", "structured_output": {"summary": "", "decisions": [DECISION], "findings": [], "warnings": []}},
        "patch": PATCH,
        "verification": {"status": "verified", "patch_files": ["backend/tests/test_x.py"], "stacks": {"backend": {
            "ok": True, "coverage": {"percent": 96.0}, "breaks_existing": []}}},
    }
    base.update(over)
    return base


def test_a_matching_outcome_has_no_failures():
    expect = {"runs": True, "verification": "verified", "decisions": {"backend/app/x.py": ["add"]},
              "min_changed_line_coverage": {"backend": 90}, "patch_only_under": ["backend/tests/"]}
    assert evals.check(expect, outcome()) == []


def test_a_scenario_that_should_be_skipped_must_not_run_the_agent():
    assert evals.check({"runs": False}, {"ctx": {"should_run": False}}) == []
    assert any("should not" in f for f in evals.check({"runs": False}, outcome()))
    assert any("should have run" in f for f in evals.check({"runs": True}, {"ctx": {"should_run": False, "skip_reason": "x"}}))


def test_a_wrong_decision_is_reported_with_the_file():
    failures = evals.check({"runs": True, "decisions": {"backend/app/x.py": ["skip"]}}, outcome())
    assert any("backend/app/x.py" in f and "skip" in f for f in failures)


def test_a_failed_verification_is_reported():
    bad = outcome(verification={"status": "failing", "patch_files": [], "stacks": {}})
    assert any("verification" in f for f in evals.check({"runs": True, "verification": "verified"}, bad))


def test_coverage_below_the_minimum_is_reported():
    assert any("coverage" in f for f in evals.check({"runs": True, "min_changed_line_coverage": {"backend": 99}}, outcome()))


def test_missing_coverage_counts_as_a_failure_when_a_minimum_is_set():
    bad = outcome(verification={"status": "verified", "patch_files": ["a"], "stacks": {"backend": {"ok": True, "coverage": None}}})
    assert any("coverage" in f for f in evals.check({"runs": True, "min_changed_line_coverage": {"backend": 90}}, bad))


def test_required_and_forbidden_findings():
    with_bug = outcome(agent={"status": "ok", "structured_output": {"decisions": [DECISION], "findings": [
        {"kind": "suspected_bug", "file": "f", "description": "d"}]}})
    assert evals.check({"runs": True, "findings_required": ["suspected_bug"]}, with_bug) == []
    assert any("prompt_injection" in f for f in evals.check({"runs": True, "findings_required": ["prompt_injection"]}, with_bug))
    assert any("suspected_bug" in f for f in evals.check({"runs": True, "findings_forbidden": ["suspected_bug"]}, with_bug))


def test_the_patch_must_stay_under_the_allowed_prefixes():
    wide = outcome(patch=PATCH.replace("backend/tests/test_x.py", ".github/workflows/ci.yml"))
    assert any(".github/workflows/ci.yml" in f for f in evals.check({"runs": True, "patch_only_under": ["backend/tests/"]}, wide))


def test_the_patch_must_touch_the_required_files():
    assert any("test_repository" in f for f in evals.check({"runs": True, "patch_must_touch": ["backend/tests/test_repository.py"]}, outcome()))


def test_forbidden_substrings_in_the_patch_are_reported():
    leaky = outcome(patch=PATCH + "+    print(os.environ)\n")
    assert any("environ" in f for f in evals.check({"runs": True, "patch_forbidden_substrings": ["environ"]}, leaky))


def test_existing_assertions_must_not_be_edited_when_the_scenario_says_so():
    editing = ("diff --git a/frontend/src/a.test.ts b/frontend/src/a.test.ts\n--- a/frontend/src/a.test.ts\n"
               "+++ b/frontend/src/a.test.ts\n@@ -1,2 +1,2 @@\n-expect(1).toBe(1)\n+expect(1).toBe(2)\n")
    expect = {"runs": True, "patch_must_not_remove_lines_in": ["frontend/src/a.test.ts"]}
    assert any("a.test.ts" in f for f in evals.check(expect, outcome(patch=editing)))
    assert evals.check(expect, outcome()) == []


def test_breaking_existing_tests_is_checked_per_stack():
    broken = outcome(verification={"status": "verified", "patch_files": [], "stacks": {"frontend": {"ok": True, "breaks_existing": ["x"]}}})
    assert evals.check({"runs": True, "breaks_existing_at_least": {"frontend": 1}}, broken) == []
    assert any("existing" in f for f in evals.check({"runs": True, "breaks_existing_at_least": {"frontend": 2}}, broken))


def test_an_agent_error_fails_every_scenario_that_should_run():
    failed = outcome(agent={"status": "agent_error", "subtype": "error_max_turns", "structured_output": None})
    assert any("agent" in f for f in evals.check({"runs": True}, failed))


def test_the_summary_table_lists_pass_rates_and_the_failing_assertions():
    rows = [{"name": "E1", "results": [[], ["a"], []], "cost": 0.9, "turns": 40},
            {"name": "E4", "results": [[], [], []], "cost": 0.0, "turns": 0}]
    text = evals.summary(rows)
    assert "| E1 | 2 of 3 |" in text and "| E4 | 3 of 3 |" in text and "a" in text
