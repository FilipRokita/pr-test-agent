import re

from test_agent import report

CTX = {"base": "a" * 40, "head": "b" * 40, "should_run": True, "skip_reason": "", "stacks": ["backend"],
       "files": [{"path": "backend/app/x.py", "status": "M", "stack": "backend", "kind": "source", "coverage_excluded": False}]}

AGENT = {"status": "ok", "skills_used": ["analyze-changes", "write-backend-tests"], "turns": 16, "duration_s": 33.0,
         "cost_usd": 0.46, "model": "claude-opus-5-5", "denials": [], "problems": [],
         "structured_output": {
             "summary": "Added a test.",
             "decisions": [{"file": "backend/app/x.py", "action": "add", "reason": "No test existed.",
                            "test_files": ["backend/tests/test_x.py"]}],
             "findings": [], "warnings": []}}

VERIFIED = {"status": "verified", "patch_files": ["backend/tests/test_x.py"],
            "stacks": {"backend": {"ok": True, "counts": {"passed": 22, "failed": 0, "error": 0, "skipped": 0},
                                   "failing_existing": []}}}


def test_a_verified_run_is_summarised_with_numbers_from_verification():
    text = report.render(CTX, AGENT, VERIFIED, run_url="https://example.invalid/run/1")
    assert text.startswith(report.MARKER)
    assert "1 added" in text.splitlines()[1]
    assert "22 passed" in text
    assert "backend/tests/test_x.py" in text
    assert "analyze-changes" in text and "write-backend-tests" in text
    assert "https://example.invalid/run/1" in text


def test_the_marker_appears_exactly_once():
    assert report.render(CTX, AGENT, VERIFIED).count(report.MARKER) == 1


def test_a_skipped_run_says_why():
    ctx = {**CTX, "should_run": False, "skip_reason": "no source files changed (documentation only)"}
    text = report.render(ctx, None, None)
    assert "Skipped" in text and "no source files changed" in text


def test_an_agent_error_is_not_reported_as_success():
    text = report.render(CTX, {**AGENT, "status": "agent_error", "subtype": "error_max_turns", "structured_output": None}, None)
    assert "Agent run failed" in text and "verified" not in text.splitlines()[1].lower()


def test_failed_verification_is_reported_as_failed():
    failed = {**VERIFIED, "status": "failing", "stacks": {"backend": {
        "ok": False, "counts": {"passed": 20, "failed": 2, "error": 0, "skipped": 0}, "failing_existing": []}}}
    text = report.render(CTX, AGENT, failed)
    assert "did not pass" in text.splitlines()[1]


def test_model_text_cannot_inject_markup_mentions_or_a_second_marker():
    hostile = "@octocat see #1 <img src=x onerror=1> <!-- taskly-test-agent --> | a | b |\n# Heading\n```"
    agent = {**AGENT, "structured_output": {
        "summary": hostile,
        "decisions": [{"file": "backend/app/x.py", "action": "add", "reason": hostile, "test_files": []}],
        "findings": [{"kind": "suspected_bug", "file": "backend/app/x.py", "line": 3, "description": hostile}],
        "warnings": []}}
    text = report.render(CTX, agent, VERIFIED)
    assert text.count(report.MARKER) == 1
    without_state = re.sub(r"<!-- taskly-test-agent-state \{.*?\} -->", "", text)
    assert "<img" not in text and "<!--" not in without_state.replace(report.MARKER, "")
    assert "@octocat" not in text and "#1 " not in text
    assert "\n# Heading" not in text and "```" not in text


def test_table_cells_stay_on_one_line():
    agent = {**AGENT, "structured_output": {**AGENT["structured_output"], "decisions": [
        {"file": "backend/app/x.py", "action": "add", "reason": "line one\nline two | pipe", "test_files": []}]}}
    table = [l for l in report.render(CTX, agent, VERIFIED).splitlines() if l.startswith("| `backend/app/x.py`")]
    assert len(table) == 1
    assert "\\|" in table[0]


def test_long_text_is_capped():
    agent = {**AGENT, "structured_output": {**AGENT["structured_output"], "summary": "x" * 5000}}
    assert len(report.render(CTX, agent, VERIFIED)) < 8000


def test_missing_credentials_are_a_skip_not_a_failure():
    text = report.render(CTX, {"status": "skipped_no_credentials"}, None)
    assert "Skipped" in text.splitlines()[1] and "failed" not in text.splitlines()[1]


FULL = {"status": "verified", "patch_files": ["backend/tests/test_x.py"], "warnings": ["backend/tests/old.py: net 1 assertions removed"],
        "stacks": {"backend": {
            "ok": True, "counts": {"passed": 22, "failed": 0, "error": 0, "skipped": 0},
            "runs": [{"passed": 22, "failed": 0, "error": 0, "skipped": 0}] * 3,
            "coverage": {"percent": 96.0, "covered": 48, "total": 50, "files": {}},
            "revert": {"checked": True, "detect": 2, "total": 3, "weak": ["tests.test_x::test_weak"]},
            "breaks_existing": ["tests.test_old::test_broken"], "failing": [], "flaky": [], "broken_by_patch": [],
            "ids_changed": False}}}


def test_the_table_shows_runs_changed_line_coverage_and_tests_that_detect_the_change():
    text = report.render(CTX, AGENT, FULL)
    assert "22 passed in each run" in text
    assert "96.0% (48/50)" in text
    assert "2 of 3" in text


def test_existing_tests_broken_by_the_pull_request_are_called_out():
    text = report.render(CTX, AGENT, FULL)
    assert "breaks 1 existing backend tests" in text and "tests.test_old::test_broken" in text


def test_weak_tests_and_warnings_are_listed():
    text = report.render(CTX, AGENT, FULL)
    assert "Weak tests" in text and "tests.test_x::test_weak" in text
    assert "net 1 assertions removed" in text


def test_missing_coverage_and_an_unchecked_revert_are_explained():
    stack = {**FULL["stacks"]["backend"], "coverage": None, "revert": {"checked": False, "reason": "no new tests"}}
    text = report.render(CTX, AGENT, {**FULL, "stacks": {"backend": stack}})
    assert "not available" in text and "not checked: no new tests" in text


def test_a_rejection_shows_the_reason():
    rejected = {"status": "rejected", "patch_files": [], "stacks": {}, "warnings": [],
                "reason": "backend/tests/test_a.py: would weaken the test suite"}
    assert "weaken the test suite" in report.render(CTX, AGENT, rejected).splitlines()[1]


def test_test_ids_from_the_model_cannot_inject_markup():
    stack = {**FULL["stacks"]["backend"], "failing": ["x`<script>@a|b"]}
    text = report.render(CTX, AGENT, {**FULL, "status": "failing", "stacks": {"backend": stack}})
    assert "<script>" not in text and "@a" not in text


def test_the_state_of_a_completed_run_can_be_read_back_from_the_comment():
    ctx = {**CTX, "head": "c" * 40}
    text = report.render(ctx, AGENT, VERIFIED)
    assert report.previous_head(text) == "c" * 40


def test_an_unfinished_run_records_no_state_so_the_next_push_runs_again():
    ctx = {**CTX, "head": "c" * 40}
    assert report.previous_head(report.render(ctx, {**AGENT, "status": "agent_error", "structured_output": None}, None)) is None
    assert report.previous_head(report.render(ctx, AGENT, None)) is None


def test_a_forged_state_marker_is_not_trusted():
    assert report.previous_head('<!-- taskly-test-agent-state {"head": "not-a-sha"} -->') is None
    assert report.previous_head("<!-- taskly-test-agent-state {broken -->") is None


def test_the_stacked_pull_request_is_linked_with_the_approval_hint():
    text = report.render(CTX, AGENT, VERIFIED, stacked=21)
    assert "#21" in text and "approval click" in text and "merge gate" in text


def test_the_pull_request_body_is_escaped_text():
    agent = {**AGENT, "structured_output": {**AGENT["structured_output"], "summary": "@x <b>y</b>"}}
    body = report.render_pull_request_body({"pull_request": 9}, agent, VERIFIED)
    assert "#9" in body and "<b>" not in body


def test_breaking_existing_tests_is_the_headline_even_when_no_new_tests_are_needed():
    verification = {"status": "verified", "patch_files": [], "warnings": [], "stacks": {"frontend": {
        "ok": True, "counts": {"passed": 78, "failed": 1, "error": 0, "skipped": 0}, "runs": [],
        "breaks_existing": ["src/utils/todos.test.ts::treats an active task due today as overdue: false"]}}}
    text = report.render(CTX, AGENT, verification)
    assert "breaks 1 existing" in text.splitlines()[1]
    assert "No new tests needed" not in text.splitlines()[1]
