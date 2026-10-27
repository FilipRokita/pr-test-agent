"""Run the backend or frontend tests inside the sandbox and report structured results."""

import os
import shutil
from pathlib import Path

from . import policy, results, sandbox

STACKS = ("backend", "frontend")
OUTPUT_TAIL = 6000


class ToolError(ValueError):
    pass


def normalise_paths(root: Path, stack: str, given: list[str]) -> list[str]:
    """Accept only writable test files and return them relative to the stack directory."""
    if stack not in STACKS:
        raise ToolError(f"unknown stack: {stack}")
    relative = []
    for item in given:
        path = Path(item)
        if path.is_absolute() or ".." in path.parts:
            raise ToolError(f"path not allowed: {item}")
        if path.parts and path.parts[0] == stack:
            path = Path(*path.parts[1:])
        if not policy.can_write(root, root / stack / path):
            raise ToolError(f"not a test file: {item}")
        relative.append(path.as_posix())
    return relative


def backend_command(paths: list[str], *, coverage: bool, out_dir: Path) -> list[str]:
    cmd = ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "randomly",
           f"--junitxml={out_dir}/junit.xml"]
    if coverage:
        cmd += ["--cov=app", f"--cov-report=xml:{out_dir}/coverage.xml",
                f"--cov-report=json:{out_dir}/coverage.json", "--cov-report=term-missing"]
    return [*cmd, *paths]


def frontend_command(paths: list[str], *, coverage: bool, out_dir: Path) -> list[str]:
    cmd = ["npx", "vitest", "run", "--configLoader", "runner", "--sequence.shuffle",
           "--reporter=default", "--reporter=junit", f"--outputFile.junit={out_dir}/junit.xml"]
    if coverage:
        cmd += ["--coverage", f"--coverage.reportsDirectory={out_dir}/cov",
                "--coverage.reporter=lcov", "--coverage.reporter=text"]
    return [*cmd, *paths]


def _path_dirs(root: Path, stack: str) -> list[str]:
    node = shutil.which("node")
    dirs = [str(Path(os.path.realpath(node)).parent)] if node else []
    if stack == "backend":
        dirs.insert(0, str(root / "backend" / ".venv" / "bin"))
    return dirs


def _tail(text: str) -> str:
    return text[-OUTPUT_TAIL:]


def run_stack(root: Path, stack: str, paths: list[str], *, coverage: bool, out_dir: Path,
              timeout: int = 600) -> dict:
    """Run one stack's tests. `out_dir` must come from sandbox.prepare_out_dir."""
    root = Path(root)
    selected = normalise_paths(root, stack, paths)
    cwd = root / stack
    dirs = _path_dirs(root, stack)
    outcome = {"stack": stack, "typecheck_ok": None, "typecheck_output": ""}

    if stack == "frontend":
        typecheck = sandbox.run(["npx", "tsc", "--noEmit", "-p", "."], cwd=cwd, out_dir=out_dir,
                                path_dirs=dirs, timeout=timeout)
        outcome["typecheck_ok"] = typecheck.returncode == 0
        outcome["typecheck_output"] = "" if typecheck.returncode == 0 else _tail(typecheck.stdout + typecheck.stderr)
        cmd = frontend_command(selected, coverage=coverage, out_dir=out_dir)
    else:
        cmd = backend_command(selected, coverage=coverage, out_dir=out_dir)

    proc = sandbox.run(cmd, cwd=cwd, out_dir=out_dir, path_dirs=dirs, timeout=timeout)
    outcome["exit_code"] = proc.returncode
    outcome["output"] = _tail(proc.stdout + proc.stderr)
    try:
        parsed = results.parse_junit(sandbox.read_output(out_dir, "junit.xml"))
    except results.ReportError as error:
        outcome.update(ok=False, counts=None, tests=[], error=str(error))
        return outcome
    outcome.update(
        ok=proc.returncode == 0 and parsed["counts"]["failed"] == 0 and parsed["counts"]["error"] == 0,
        counts=parsed["counts"],
        tests=parsed["tests"],
    )
    return outcome
