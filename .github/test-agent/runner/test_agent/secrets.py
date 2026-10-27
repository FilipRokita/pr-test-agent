"""Scan proposed test files for secrets with gitleaks before anything is published."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / ".gitleaks.toml"


class ScanError(RuntimeError):
    pass


def scan(root: Path | str, files: list[str], *, binary: str | None = None) -> list[dict]:
    """Return findings for `files` (repository-relative). Findings never contain the secret itself."""
    binary = binary or os.environ.get("GITLEAKS_BIN") or "gitleaks"
    findings = []
    with tempfile.TemporaryDirectory(prefix="gitleaks-") as work:
        for file in files:
            report = Path(work) / "report.json"
            try:
                proc = subprocess.run(
                    [binary, "dir", str(Path(root) / file), "--no-banner", "--redact", "--config", str(CONFIG),
                     "--report-format", "json", "--report-path", str(report)],
                    capture_output=True, text=True, check=False)
            except OSError as error:
                raise ScanError(f"gitleaks could not run: {error}") from error
            if proc.returncode not in (0, 1):
                raise ScanError(f"gitleaks failed ({proc.returncode}): {proc.stderr.strip()[:200]}")
            if proc.returncode == 1 and report.exists():
                for item in json.loads(report.read_text() or "[]"):
                    findings.append({"file": file, "rule": item.get("RuleID", ""), "line": item.get("StartLine")})
    return findings
