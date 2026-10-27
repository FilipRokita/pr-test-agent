"""Parse JUnit XML written by pytest and Vitest into per-test outcomes.

The XML is produced by code the model wrote, so it is untrusted input: parsed with defusedxml.
"""

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

MAX_MESSAGE = 600


class ReportError(ValueError):
    pass


def parse_junit(xml_text: str | None) -> dict:
    if not xml_text:
        raise ReportError("test report is missing or empty")
    try:
        root = ElementTree.fromstring(xml_text)
    except (ElementTree.ParseError, DefusedXmlException) as error:
        raise ReportError(f"test report is not valid XML: {error}") from error

    tests = []
    for case in root.iter("testcase"):
        classname = case.get("classname") or case.get("file") or ""
        outcome, message = "passed", ""
        if case.find("failure") is not None:
            node = case.find("failure")
            outcome, message = "failed", node.get("message") or (node.text or "")
        elif case.find("error") is not None:
            node = case.find("error")
            outcome, message = "error", node.get("message") or (node.text or "")
        elif case.find("skipped") is not None:
            outcome = "skipped"
            message = case.find("skipped").get("message") or ""
        tests.append({
            "id": f"{classname}::{case.get('name', '')}",
            "outcome": outcome,
            "message": message.strip()[:MAX_MESSAGE],
        })

    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for test in tests:
        counts[test["outcome"]] += 1
    return {"tests": tests, "counts": counts}


def ids(parsed: dict) -> set[str]:
    return {test["id"] for test in parsed["tests"]}
