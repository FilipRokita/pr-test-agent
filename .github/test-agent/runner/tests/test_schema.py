from test_agent import schema


def _result(decisions, findings=None):
    return {"summary": "s", "decisions": decisions, "findings": findings or []}


def _decision(path, action="add"):
    return {"file": path, "action": action, "reason": "r", "test_files": []}


def test_every_changed_source_file_keeps_exactly_one_decision():
    result = schema.normalise(
        _result([_decision("backend/app/a.py"), _decision("backend/app/b.py", "skip")]),
        ["backend/app/a.py", "backend/app/b.py"],
    )
    assert [d["file"] for d in result["decisions"]] == ["backend/app/a.py", "backend/app/b.py"]
    assert result["warnings"] == []


def test_a_missing_decision_is_filled_as_skip_with_a_warning():
    result = schema.normalise(_result([_decision("backend/app/a.py")]), ["backend/app/a.py", "backend/app/b.py"])
    filled = result["decisions"][1]
    assert filled["file"] == "backend/app/b.py" and filled["action"] == "skip"
    assert "no decision" in filled["reason"]
    assert any("backend/app/b.py" in w for w in result["warnings"])


def test_duplicate_decisions_keep_the_first():
    result = schema.normalise(
        _result([_decision("backend/app/a.py", "add"), _decision("backend/app/a.py", "skip")]),
        ["backend/app/a.py"],
    )
    assert [d["action"] for d in result["decisions"]] == ["add"]
    assert any("duplicate" in w for w in result["warnings"])


def test_decisions_for_files_that_did_not_change_are_dropped():
    result = schema.normalise(
        _result([_decision("backend/app/a.py"), _decision("backend/app/never.py")]), ["backend/app/a.py"]
    )
    assert [d["file"] for d in result["decisions"]] == ["backend/app/a.py"]
    assert any("backend/app/never.py" in w for w in result["warnings"])


def test_missing_sections_default_to_empty():
    result = schema.normalise({}, ["backend/app/a.py"])
    assert result["summary"] == "" and result["findings"] == []
    assert result["decisions"][0]["action"] == "skip"


def test_the_schema_requires_the_three_sections_and_no_extras():
    assert schema.SCHEMA["required"] == ["summary", "decisions", "findings"]
    assert schema.SCHEMA["additionalProperties"] is False
    kinds = schema.SCHEMA["properties"]["findings"]["items"]["properties"]["kind"]["enum"]
    assert {"suspected_bug", "spec_mismatch", "untestable", "prompt_injection", "dropped_test"} == set(kinds)
