"""The agent's structured answer and how the runner makes it complete.

Numbers (tests, coverage) never come from this answer; they come from the verification job.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "decisions", "findings"],
    "properties": {
        "summary": {"type": "string", "maxLength": 600},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["file", "action", "reason", "test_files"],
                "properties": {
                    "file": {"type": "string"},
                    "action": {"enum": ["add", "update", "skip"]},
                    "reason": {"type": "string", "maxLength": 300},
                    "test_files": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "file", "description"],
                "properties": {
                    "kind": {"enum": ["suspected_bug", "spec_mismatch", "untestable", "prompt_injection", "dropped_test"]},
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "description": {"type": "string", "maxLength": 600},
                    "expected_behavior": {"type": "string", "maxLength": 300},
                    "suggested_test": {"type": "string", "maxLength": 3000},
                },
            },
        },
    },
}


def normalise(result: dict, changed_sources: list[str]) -> dict:
    """Make sure every changed source file has exactly one decision; report what had to be repaired."""
    warnings = []
    seen = {}
    for decision in result.get("decisions", []):
        path = decision.get("file")
        if path not in changed_sources:
            warnings.append(f"decision for a file that did not change was dropped: {path}")
        elif path in seen:
            warnings.append(f"duplicate decision ignored: {path}")
        else:
            seen[path] = decision

    decisions = []
    for path in changed_sources:
        if path in seen:
            decisions.append(seen[path])
        else:
            warnings.append(f"no decision returned for {path}")
            decisions.append({"file": path, "action": "skip", "reason": "no decision returned", "test_files": []})

    return {
        "summary": result.get("summary", ""),
        "decisions": decisions,
        "findings": result.get("findings", []),
        "warnings": warnings,
    }
