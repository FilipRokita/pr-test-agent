import pytest

from test_agent import results

PYTEST_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="1" skipped="1" tests="4">
<testcase classname="tests.features.todos.test_router" name="test_ok" file="tests/features/todos/test_router.py" time="0.01"/>
<testcase classname="tests.features.todos.test_router" name="test_bad[a]" time="0.02">
  <failure message="assert 1 == 2">E assert 1 == 2</failure>
</testcase>
<testcase classname="tests.core.test_x" name="test_skip" time="0.0"><skipped type="pytest.skip" message="why"/></testcase>
<testcase classname="tests.core.test_x" name="test_boom" time="0.0"><error message="ImportError: x">trace</error></testcase>
</testsuite></testsuites>"""

VITEST_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<testsuites name="vitest tests" tests="2" failures="1" errors="0" time="0.1">
<testsuite name="src/lib/http.test.ts" tests="2" failures="1">
<testcase classname="src/lib/http.test.ts" name="sends json" time="0.001"></testcase>
<testcase classname="src/lib/http.test.ts" name="maps 422" time="0.002"><failure message="expected 1 to be 2" type="AssertionError">details</failure></testcase>
</testsuite></testsuites>"""


def test_pytest_report_is_parsed_into_outcomes():
    parsed = results.parse_junit(PYTEST_XML)
    outcomes = {t["id"]: t["outcome"] for t in parsed["tests"]}
    assert outcomes == {
        "tests.features.todos.test_router::test_ok": "passed",
        "tests.features.todos.test_router::test_bad[a]": "failed",
        "tests.core.test_x::test_skip": "skipped",
        "tests.core.test_x::test_boom": "error",
    }
    assert parsed["counts"] == {"passed": 1, "failed": 1, "error": 1, "skipped": 1}


def test_failure_messages_are_kept_but_trimmed():
    parsed = results.parse_junit(PYTEST_XML)
    failed = next(t for t in parsed["tests"] if t["outcome"] == "failed")
    assert "assert 1 == 2" in failed["message"]
    long = PYTEST_XML.replace("assert 1 == 2\">E", "x" * 5000 + "\">E")
    assert all(len(t["message"]) <= results.MAX_MESSAGE for t in results.parse_junit(long)["tests"])


def test_vitest_report_is_parsed_with_file_ids():
    parsed = results.parse_junit(VITEST_XML)
    assert {t["id"]: t["outcome"] for t in parsed["tests"]} == {
        "src/lib/http.test.ts::sends json": "passed",
        "src/lib/http.test.ts::maps 422": "failed",
    }


def test_entity_expansion_attacks_are_rejected():
    bomb = """<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><testsuites>&b;</testsuites>"""
    with pytest.raises(results.ReportError):
        results.parse_junit(bomb)


def test_garbage_is_a_report_error():
    with pytest.raises(results.ReportError):
        results.parse_junit("not xml at all")


def test_missing_report_is_a_report_error():
    with pytest.raises(results.ReportError):
        results.parse_junit(None)


def test_test_ids_in_a_set_are_comparable_across_runs():
    first = results.parse_junit(PYTEST_XML)
    second = results.parse_junit(PYTEST_XML)
    assert results.ids(first) == results.ids(second)
