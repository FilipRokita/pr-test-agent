"""Coverage of the lines a pull request changed, measured with diff-cover on the reports the sandbox wrote."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


class CoverageError(RuntimeError):
    pass


def rewrite_lcov(lcov_text: str, stack_dir: str) -> str:
    """Vitest writes paths relative to frontend/; diff-cover needs paths relative to the repository root."""
    out = []
    for line in lcov_text.splitlines():
        if line.startswith("SF:") and not line.startswith(f"SF:{stack_dir}/"):
            line = f"SF:{stack_dir}/{line[3:]}"
        out.append(line)
    return "\n".join(out) + "\n"


def changed_lines(root: Path | str, report: Path | str, base: str, stack: str = "backend") -> dict:
    """Coverage of the changed executable lines per file; `percent` is None when nothing executable changed."""
    root, report = Path(root), Path(report)
    with tempfile.TemporaryDirectory(prefix="diffcover-") as work:
        source = report
        if stack == "frontend":
            source = Path(work) / "lcov.info"
            source.write_text(rewrite_lcov(report.read_text(), "frontend"))
        output = Path(work) / "report.json"
        proc = subprocess.run(
            [sys.executable, "-m", "diff_cover.diff_cover_tool", str(source), "--compare-branch", base,
             "--format", f"json:{output}", "-q"],
            cwd=root, capture_output=True, text=True, check=False)
        if proc.returncode not in (0, 1) or not output.exists():
            raise CoverageError(f"diff-cover failed: {proc.stderr.strip()[:300]}")
        stats = json.loads(output.read_text()).get("src_stats", {})

    files = {}
    covered = total = 0
    for path, item in stats.items():
        done, missed = len(item["covered_lines"]), len(item["violation_lines"])
        covered, total = covered + done, total + done + missed
        files[path] = {"covered": done, "total": done + missed, "uncovered": sorted(item["violation_lines"])}
    return {"covered": covered, "total": total, "percent": round(100 * covered / total, 1) if total else None,
            "files": files}
