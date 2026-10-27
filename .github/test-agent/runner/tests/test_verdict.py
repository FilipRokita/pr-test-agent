import pytest

from test_agent import verdict


def outcomes(**outcomes):
    return [{"id": name.replace("__", "::"), "outcome": outcome, "message": ""} for name, outcome in outcomes.items()]


def file_of(test_id):
    return test_id.split("::")[0] + ".py"


TOUCHED = {"new_file.py"}


def evaluate(baseline, runs):
    return verdict.evaluate(baseline, runs, TOUCHED, file_of)


def test_new_passing_tests_in_three_runs_are_ok():
    base = outcomes(old_file__a="passed")
    run = outcomes(old_file__a="passed", new_file__n="passed")
    result = evaluate(base, [run, run, run])
    assert result["ok"] is True
    assert result["new_tests"] == ["new_file::n"]
    assert result["failing"] == result["flaky"] == result["broken_by_patch"] == []


def test_a_touched_test_that_fails_in_any_run_fails_the_patch():
    base = outcomes(old_file__a="passed")
    good = outcomes(old_file__a="passed", new_file__n="passed")
    bad = outcomes(old_file__a="passed", new_file__n="failed")
    result = evaluate(base, [good, bad, good])
    assert result["ok"] is False and result["failing"] == ["new_file::n"]


def test_a_skipped_new_test_does_not_count_as_passing():
    base = outcomes(old_file__a="passed")
    run = outcomes(old_file__a="passed", new_file__n="skipped")
    assert evaluate(base, [run, run, run])["failing"] == ["new_file::n"]


def test_a_test_that_changes_outcome_between_runs_is_flaky():
    base = outcomes(old_file__a="passed")
    ok = outcomes(old_file__a="passed")
    flaky = outcomes(old_file__a="failed")
    result = evaluate(base, [ok, flaky, ok])
    assert result["ok"] is False and result["flaky"] == ["old_file::a"]


def test_an_untouched_test_that_passed_before_and_fails_after_is_broken_by_the_patch():
    base = outcomes(old_file__a="passed")
    after = outcomes(old_file__a="failed")
    result = evaluate(base, [after, after, after])
    assert result["ok"] is False and result["broken_by_patch"] == ["old_file::a"]


def test_failures_that_already_existed_are_reported_but_do_not_fail_the_patch():
    base = outcomes(old_file__a="failed", old_file__b="passed")
    after = outcomes(old_file__a="failed", old_file__b="passed", new_file__n="passed")
    result = evaluate(base, [after, after, after])
    assert result["ok"] is True
    assert result["breaks_existing"] == ["old_file::a"]


def test_fixing_a_failing_test_in_a_touched_file_is_fine():
    base = outcomes(new_file__t="failed", old_file__b="passed")
    after = outcomes(new_file__t="passed", old_file__b="passed")
    result = evaluate(base, [after, after, after])
    assert result["ok"] is True and result["breaks_existing"] == []


def test_tests_disappearing_from_untouched_files_are_rejected():
    base = outcomes(old_file__a="passed", old_file__b="passed")
    after = outcomes(old_file__a="passed")
    result = evaluate(base, [after, after, after])
    assert result["ok"] is False and result["ids_changed"] is True


def test_tests_appearing_in_untouched_files_are_rejected():
    base = outcomes(old_file__a="passed")
    after = outcomes(old_file__a="passed", other_file__x="passed")
    result = evaluate(base, [after, after, after])
    assert result["ok"] is False and result["ids_changed"] is True


def test_the_test_module_is_found_from_the_id_for_both_stacks(tmp_path):
    (tmp_path / "backend/tests/features").mkdir(parents=True)
    (tmp_path / "backend/tests/features/test_router.py").write_text("")
    (tmp_path / "frontend/src/lib").mkdir(parents=True)
    (tmp_path / "frontend/src/lib/http.test.ts").write_text("")
    assert verdict.test_file(tmp_path, "backend", "tests.features.test_router::test_a") == "backend/tests/features/test_router.py"
    assert verdict.test_file(tmp_path, "backend", "tests.features.test_router.TestClass::test_a") == "backend/tests/features/test_router.py"
    assert verdict.test_file(tmp_path, "frontend", "src/lib/http.test.ts::sends json") == "frontend/src/lib/http.test.ts"
    assert verdict.test_file(tmp_path, "backend", "tests.missing.test_x::test_a") == "backend/tests/missing/test_x.py"


def test_renaming_a_test_in_a_touched_file_is_not_a_failure():
    base = outcomes(new_file__old_name="passed", old_file__a="passed")
    after = outcomes(new_file__new_name="passed", old_file__a="passed")
    result = evaluate(base, [after, after, after])
    assert result["ok"] is True
    assert result["removed"] == ["new_file::old_name"] and result["new_tests"] == ["new_file::new_name"]


def test_a_test_that_exists_in_some_runs_only_is_still_inconsistent():
    base = outcomes(old_file__a="passed")
    with_it = outcomes(old_file__a="passed", new_file__n="passed")
    result = evaluate(base, [with_it, base_run := outcomes(old_file__a="passed"), with_it])
    assert result["ok"] is False and "new_file::n" in result["flaky"]
