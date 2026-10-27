import pytest

from test_agent import guard


def new_file(path, body, mode="100644"):
    lines = body.splitlines()
    added = "".join(f"+{line}\n" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\nnew file mode {mode}\nindex 0000000..1111111\n--- /dev/null\n+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n{added}"
    )


GOOD_PY = "def test_ok():\n    assert 1 + 1 == 2\n"
GOOD_TS = "it('adds', () => {\n  expect(1 + 1).toBe(2)\n})\n"


def test_a_plain_assertion_test_passes():
    assert guard.check(new_file("backend/tests/test_a.py", GOOD_PY)).violations == []
    assert guard.check(new_file("frontend/src/lib/a.test.ts", GOOD_TS)).violations == []


@pytest.mark.parametrize(
    "line",
    [
        "@pytest.mark.skip(reason='later')",
        "@pytest.mark.skipif(True, reason='x')",
        "@pytest.mark.xfail",
        "pytest.skip('no')",
        "pytest.importorskip('x')",
        "pytestmark = pytest.mark.skip",
        "collect_ignore = ['x']",
        "@unittest.skip('x')",
        "x = 1  # pragma: no cover",
        "pytest.param(1, marks=pytest.mark.skip)",
    ],
)
def test_python_markers_that_weaken_tests_are_rejected(line):
    body = f"import pytest\n{line}\ndef test_x():\n    assert True\n"
    result = guard.check(new_file("backend/tests/test_a.py", body))
    assert any("weaken" in v for v in result.violations), result.violations


@pytest.mark.parametrize(
    "line",
    [
        "it.skip('x', () => {})",
        "describe.skip('x', () => {})",
        "it.skipIf(true)('x', () => {})",
        "it.only('x', () => {})",
        "test.only('x', () => {})",
        "it.todo('later')",
        "it.fails('x', () => {})",
        "xit('x', () => {})",
        "xdescribe('x', () => {})",
        "/* istanbul ignore next */",
        "/* c8 ignore next */",
        "/* v8 ignore next */",
    ],
)
def test_typescript_markers_that_weaken_tests_are_rejected(line):
    body = f"{line}\nit('real', () => {{ expect(1).toBe(1) }})\n"
    result = guard.check(new_file("frontend/src/lib/a.test.ts", body))
    assert any("weaken" in v for v in result.violations), result.violations


def test_a_removed_marker_line_is_not_flagged():
    patch = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\nindex 1..2 100644\n"
        "--- a/backend/tests/test_a.py\n+++ b/backend/tests/test_a.py\n@@ -1,3 +1,3 @@\n"
        "-@pytest.mark.skip\n+@pytest.mark.parametrize('n', [1])\n def test_a(n):\n"
    )
    assert not any("weaken" in v for v in guard.check(patch).violations)


def test_paths_outside_the_writable_area_are_rejected():
    result = guard.check(new_file("backend/app/new.py", GOOD_PY))
    assert any("backend/app/new.py" in v for v in result.violations)
    result = guard.check(new_file("backend/tests/conftest.py", GOOD_PY))
    assert any("conftest.py" in v for v in result.violations)


def test_a_python_test_without_an_assertion_is_rejected():
    body = "def test_nothing():\n    x = 1 + 1\n"
    result = guard.check(new_file("backend/tests/test_a.py", body))
    assert any("no assertion" in v and "test_nothing" in v for v in result.violations)


@pytest.mark.parametrize(
    "body",
    [
        "def test_a():\n    assert 1\n",
        "def test_a():\n    mock.assert_called_once_with(1)\n",
        "def test_a():\n    with pytest.raises(ValueError):\n        int('x')\n",
        "def test_a():\n    with pytest.warns(UserWarning):\n        pass\n",
        "async def test_a():\n    assert await f()\n",
    ],
)
def test_accepted_python_assertion_forms(body):
    assert guard.check(new_file("backend/tests/test_a.py", body)).violations == []


def test_a_typescript_test_without_expect_is_rejected():
    body = "it('does nothing', () => {\n  const x = 1\n})\n"
    result = guard.check(new_file("frontend/src/lib/a.test.ts", body))
    assert any("no assertion" in v for v in result.violations)


def test_only_tests_touched_by_the_patch_need_an_assertion():
    patch = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\nindex 1..2 100644\n"
        "--- a/backend/tests/test_a.py\n+++ b/backend/tests/test_a.py\n@@ -1,2 +1,5 @@\n"
        " def test_old():\n     x = 1\n+\n+def test_new():\n+    assert 1\n"
    )
    assert guard.check(patch).violations == []


def test_binary_files_symlinks_and_mode_changes_are_rejected():
    binary = ("diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\nnew file mode 100644\n"
              "index 0000000..1111111\nGIT binary patch\nliteral 4\nLcmZQz\n\n")
    assert any("binary" in v for v in guard.check(binary).violations)
    assert any("symlink" in v or "mode" in v for v in guard.check(new_file("backend/tests/test_a.py", GOOD_PY, mode="120000")).violations)
    changed = ("diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\nold mode 100644\nnew mode 100755\n")
    assert any("mode" in v for v in guard.check(changed).violations)


def test_init_files_must_stay_empty():
    result = guard.check(new_file("backend/tests/features/__init__.py", "import os"))
    assert any("__init__" in v for v in result.violations)
    empty = ("diff --git a/backend/tests/features/__init__.py b/backend/tests/features/__init__.py\n"
             "new file mode 100644\nindex 0000000..e69de29\n")
    assert guard.check(empty).violations == []


def test_deleting_a_test_file_is_a_warning_not_a_violation():
    patch = ("diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\ndeleted file mode 100644\n"
             "index 1111111..0000000\n--- a/backend/tests/test_a.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-def test_a():\n-    assert 1\n")
    result = guard.check(patch)
    assert result.violations == []
    assert any("deleted" in w for w in result.warnings)


def test_removing_assertions_is_a_warning():
    patch = (
        "diff --git a/backend/tests/test_a.py b/backend/tests/test_a.py\nindex 1..2 100644\n"
        "--- a/backend/tests/test_a.py\n+++ b/backend/tests/test_a.py\n@@ -1,4 +1,2 @@\n"
        " def test_a():\n-    assert 1\n-    assert 2\n+    assert 1\n"
    )
    result = guard.check(patch)
    assert any("assertions" in w for w in result.warnings)


MULTILINE = (
    "@pytest.mark.parametrize(\n    ('a', 'b'),\n    [(1, 1), (2, 2)],\n)\n"
    "def test_long_signature(\n    model_factory,\n    todo_values,\n    a,\n    b,\n):\n"
    "    session = Mock()\n    assert a == b\n"
)


def test_a_test_with_a_multiline_signature_and_an_assertion_is_accepted():
    assert guard.check(new_file("backend/tests/test_a.py", MULTILINE)).violations == []


def test_a_test_with_a_multiline_signature_and_no_assertion_is_still_rejected():
    body = MULTILINE.replace("    assert a == b\n", "    value = a\n")
    result = guard.check(new_file("backend/tests/test_a.py", body))
    assert any("test_long_signature has no assertion" in v for v in result.violations)


def test_the_body_of_the_next_function_does_not_count_for_this_one():
    body = "def test_one(\n    a,\n):\n    value = a\n\n\ndef test_two():\n    assert 1\n"
    result = guard.check(new_file("backend/tests/test_a.py", body))
    assert any("test_one has no assertion" in v for v in result.violations)
    assert not any("test_two" in v for v in result.violations)
