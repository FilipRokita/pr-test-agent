import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from test_agent import sandbox, tools

REPO = Path(__file__).resolve().parents[4]


def test_backend_command_runs_the_given_files_in_random_order(tmp_path):
    cmd = tools.backend_command(["tests/features/todos/test_router.py"], coverage=False, out_dir=tmp_path)
    assert cmd[:3] == ["python", "-m", "pytest"]
    assert "-p" in cmd and "randomly" in cmd
    assert f"--junitxml={tmp_path}/junit.xml" in cmd
    assert cmd[-1] == "tests/features/todos/test_router.py"
    assert not any(part.startswith("--cov") for part in cmd)


def test_backend_command_with_coverage_writes_reports_to_the_output_directory(tmp_path):
    cmd = tools.backend_command([], coverage=True, out_dir=tmp_path)
    assert "--cov=app" in cmd
    assert f"--cov-report=xml:{tmp_path}/coverage.xml" in cmd
    assert f"--cov-report=json:{tmp_path}/coverage.json" in cmd


def test_frontend_command_loads_the_config_without_writing_into_the_workspace(tmp_path):
    cmd = tools.frontend_command(["src/lib/http.test.ts"], coverage=True, out_dir=tmp_path)
    assert cmd[:3] == ["npx", "vitest", "run"]
    assert "--configLoader" in cmd and "runner" in cmd
    assert "--sequence.shuffle" in cmd
    assert f"--coverage.reportsDirectory={tmp_path}/cov" in cmd
    assert cmd[-1] == "src/lib/http.test.ts"


@pytest.mark.parametrize(
    ("stack", "given", "relative"),
    [
        ("backend", "backend/tests/features/todos/test_router.py", "tests/features/todos/test_router.py"),
        ("backend", "tests/features/todos/test_router.py", "tests/features/todos/test_router.py"),
        ("frontend", "frontend/src/lib/http.test.ts", "src/lib/http.test.ts"),
        ("frontend", "src/lib/http.test.ts", "src/lib/http.test.ts"),
    ],
)
def test_test_paths_are_normalised_per_stack(stack, given, relative):
    assert tools.normalise_paths(REPO, stack, [given]) == [relative]


@pytest.mark.parametrize(
    ("stack", "given"),
    [
        ("backend", "backend/app/features/todos/router.py"),
        ("backend", "backend/tests/conftest.py"),
        ("backend", "../../etc/passwd"),
        ("backend", "/etc/passwd"),
        ("frontend", "frontend/src/App.tsx"),
        ("frontend", "frontend/package.json"),
        ("frontend", "src/test/setup.ts"),
    ],
)
def test_only_writable_test_files_can_be_selected(stack, given):
    with pytest.raises(tools.ToolError):
        tools.normalise_paths(REPO, stack, [given])


def test_unknown_stack_is_rejected():
    with pytest.raises(tools.ToolError):
        tools.normalise_paths(REPO, "docs", [])


def _can_sandbox():
    if not (shutil.which("unshare") and shutil.which("setpriv")):
        return False
    probe = sandbox.build_command(["true"], out_dir=Path(tempfile.gettempdir()), path_dirs=[], use_sudo=os.geteuid() != 0)
    return subprocess.run(probe, capture_output=True).returncode == 0


needs_env = pytest.mark.skipif(
    not (_can_sandbox() and (REPO / "backend/.venv/bin/python").exists() and (REPO / "frontend/node_modules").exists()),
    reason="needs the sandbox, backend/.venv and frontend/node_modules",
)


@pytest.fixture
def out_dir():
    path = Path(tempfile.mkdtemp(prefix="tools-out-"))
    sandbox.prepare_out_dir(path / "out")
    yield path / "out"
    shutil.rmtree(path, ignore_errors=True)


@needs_env
def test_backend_suite_runs_in_the_sandbox_and_reports_outcomes(out_dir):
    result = tools.run_stack(REPO, "backend", [], coverage=True, out_dir=out_dir)
    assert result["ok"] is True, result["output"]
    assert result["counts"]["failed"] == 0 and result["counts"]["passed"] >= 21
    assert (out_dir / "coverage.xml").exists() and (out_dir / "coverage.json").exists()


@needs_env
def test_frontend_suite_runs_in_the_sandbox_and_reports_outcomes(out_dir):
    result = tools.run_stack(REPO, "frontend", [], coverage=True, out_dir=out_dir)
    assert result["typecheck_ok"] is True, result["typecheck_output"]
    assert result["ok"] is True, result.get("error") or result["output"]
    assert result["counts"]["failed"] == 0 and result["counts"]["passed"] >= 18
    assert (out_dir / "cov" / "lcov.info").exists()


@needs_env
def test_a_single_backend_file_can_be_selected(out_dir):
    result = tools.run_stack(REPO, "backend", ["backend/tests/features/todos/test_validators.py"],
                             coverage=False, out_dir=out_dir)
    assert result["ok"] is True, result["output"]
    assert {t["id"].split("::")[0] for t in result["tests"]} == {"tests.features.todos.test_validators"}


def test_only_frontend_files_get_a_format_check(tmp_path):
    assert tools.check_format(REPO, "backend", ["backend/tests/x.py"], tmp_path) is None
    assert tools.check_format(REPO, "frontend", [], tmp_path) is None


@needs_env
def test_the_format_check_accepts_a_formatted_file_and_rejects_an_unformatted_one(out_dir):
    good = "frontend/src/hooks/useNotice.test.ts"
    assert tools.check_format(REPO, "frontend", [good], out_dir)["ok"] is True
    bad = REPO / "frontend/src/zz_unformatted.test.ts"
    bad.write_text("it( 'a',()=>{expect(1).toBe( 1 )})\n")
    try:
        result = tools.check_format(REPO, "frontend", ["frontend/src/zz_unformatted.test.ts"], out_dir)
    finally:
        bad.unlink()
    assert result["ok"] is False and "zz_unformatted" in result["output"]
