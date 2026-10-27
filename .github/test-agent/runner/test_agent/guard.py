"""Reject proposed patches that could make a test suite look better than it is.

The agent is told not to do these things; this module checks that it did not, on the patch itself, before any
of the patch is applied or run.
"""

import re
from dataclasses import dataclass, field

from . import policy

_PY_WEAKENING = re.compile(
    r"pytest\.mark\.(skip|skipif|xfail)\b|pytest\.(skip|xfail|importorskip)\(|\bpytestmark\b|\bcollect_ignore"
    r"|\bunittest\.skip|pragma:\s*no cover"
)
_TS_WEAKENING = re.compile(
    r"\b(it|test|describe)\.(skip|skipIf|only|todo|fails|runIf)\b|\b(xit|xdescribe|xtest|fit|fdescribe)\("
    r"|istanbul ignore|c8 ignore|v8 ignore"
)
_PY_ASSERTION = re.compile(r"\bassert\b|\.assert\w*\(|pytest\.(raises|warns|deprecated_call)\b")
_TS_ASSERTION = re.compile(r"\bexpect(?:Typeof)?\(|\bassert\w*\(|\.rejects\.|\.resolves\.")
_PY_TEST_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+(test_\w+)\s*\(")
_TS_TEST_CALL = re.compile(r"^\s*(?:it|test)(?:\.each\([^)]*\))?\s*\(")


@dataclass
class Result:
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _File:
    path: str
    old_path: str
    new: bool = False
    deleted: bool = False
    binary: bool = False
    mode: str = ""
    mode_change: bool = False
    hunks: list[list[tuple[str, str]]] = field(default_factory=list)  # (marker, text) per line


def _parse(patch_text: str) -> list[_File]:
    files: list[_File] = []
    current: _File | None = None
    hunk: list[tuple[str, str]] | None = None
    for line in patch_text.splitlines():
        header = re.match(r"^diff --git a/(.+) b/(.+)$", line)
        if header:
            current = _File(path=header.group(2), old_path=header.group(1))
            files.append(current)
            hunk = None
        elif current is None:
            continue
        elif line.startswith("new file mode "):
            current.new, current.mode = True, line.split()[-1]
        elif line.startswith("deleted file mode "):
            current.deleted = True
        elif line.startswith(("old mode ", "new mode ")):
            current.mode_change = True
        elif line.startswith("GIT binary patch") or line.startswith("Binary files "):
            current.binary = True
        elif line.startswith("@@"):
            hunk = []
            current.hunks.append(hunk)
        elif hunk is not None and line[:1] in ("+", "-", " ") and not line.startswith(("+++ ", "--- ")):
            hunk.append((line[0], line[1:]))
        elif hunk is not None and line.startswith(("+++", "---")) and len(line) <= 3:
            hunk.append((line[0], line[1:]))
    return files


def _added(file: _File) -> list[str]:
    return [text for hunk in file.hunks for marker, text in hunk if marker == "+"]


def _removed(file: _File) -> list[str]:
    return [text for hunk in file.hunks for marker, text in hunk if marker == "-"]


def _python_tests_without_assertion(file: _File) -> list[str]:
    """Names of test functions that contain an added line and no assertion."""
    missing = []
    for hunk in file.hunks:
        new_side = [(marker, text) for marker, text in hunk if marker != "-"]
        index = 0
        while index < len(new_side):
            match = _PY_TEST_DEF.match(new_side[index][1])
            if not match:
                index += 1
                continue
            indent = len(match.group(1))
            end = index + 1
            while end < len(new_side):
                text = new_side[end][1]
                if text.strip() and len(text) - len(text.lstrip()) <= indent:
                    break
                end += 1
            block = new_side[index:end]
            touched = any(marker == "+" and text.strip() for marker, text in block)
            if touched and not any(_PY_ASSERTION.search(text) for _, text in block):
                missing.append(match.group(2))
            index = end
    return missing


def check(patch_text: str) -> Result:
    result = Result()
    for file in _parse(patch_text):
        path = file.path
        if not policy.is_writable_relative(path) or not policy.is_writable_relative(file.old_path):
            result.violations.append(f"{path}: outside the writable test files")
            continue
        if file.binary:
            result.violations.append(f"{path}: binary content is not allowed")
        if file.mode == "120000":
            result.violations.append(f"{path}: a symlink is not allowed")
        elif file.mode and file.mode != "100644":
            result.violations.append(f"{path}: unexpected file mode {file.mode}")
        if file.mode_change:
            result.violations.append(f"{path}: file mode changes are not allowed")
        if file.deleted:
            result.warnings.append(f"{path}: deleted test file")

        added = _added(file)
        if path.endswith("__init__.py") and any(line.strip() for line in added):
            result.violations.append(f"{path}: __init__.py files must stay empty")

        pattern = _PY_WEAKENING if path.endswith(".py") else _TS_WEAKENING
        for line in added:
            if pattern.search(line):
                result.violations.append(f"{path}: would weaken the test suite ({line.strip()[:80]})")

        if path.endswith(".py") and not path.endswith("__init__.py"):
            for name in _python_tests_without_assertion(file):
                result.violations.append(f"{path}: test {name} has no assertion")
            token = _PY_ASSERTION
        else:
            if any(_TS_TEST_CALL.match(line) for line in added) and not any(_TS_ASSERTION.search(l) for l in added):
                result.violations.append(f"{path}: added tests have no assertion")
            token = _TS_ASSERTION
        net = sum(1 for l in _removed(file) if token.search(l)) - sum(1 for l in added if token.search(l))
        if net > 0:
            result.warnings.append(f"{path}: net {net} assertions removed")
    return result
