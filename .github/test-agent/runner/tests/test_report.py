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
    assert "<img" not in text and "<!--" not in text.replace(report.MARKER, "")
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
