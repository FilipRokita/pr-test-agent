import os
import shutil
from pathlib import Path

import pytest

from test_agent import secrets

BINARY = os.environ.get("GITLEAKS_BIN") or shutil.which("gitleaks")
needs_gitleaks = pytest.mark.skipif(not BINARY, reason="gitleaks is not installed (set GITLEAKS_BIN)")


def _fake(prefix, length):
    import random
    rng = random.Random(7)
    return prefix + "".join(rng.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(length))


@needs_gitleaks
def test_a_clean_file_has_no_findings(tmp_path):
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert 1\n")
    assert secrets.scan(tmp_path, ["test_a.py"], binary=BINARY) == []


@needs_gitleaks
def test_an_anthropic_api_key_is_found(tmp_path):
    (tmp_path / "test_a.py").write_text(f'KEY = "{_fake("sk-ant-api03-", 93)}AA"\n')
    findings = secrets.scan(tmp_path, ["test_a.py"], binary=BINARY)
    assert findings and findings[0]["file"] == "test_a.py"
    assert "sk-ant" not in str(findings)


@needs_gitleaks
def test_a_claude_code_oauth_token_is_found(tmp_path):
    (tmp_path / "test_a.py").write_text(f'TOKEN = "{_fake("sk-ant-oat01-", 80)}"\n')
    findings = secrets.scan(tmp_path, ["test_a.py"], binary=BINARY)
    assert any(f["rule"] == "claude-code-oauth-token" for f in findings)


@needs_gitleaks
def test_only_the_listed_files_are_scanned(tmp_path):
    (tmp_path / "clean.py").write_text("x = 1\n")
    (tmp_path / "other.py").write_text(f'KEY = "{_fake("sk-ant-api03-", 93)}AA"\n')
    assert secrets.scan(tmp_path, ["clean.py"], binary=BINARY) == []


def test_a_missing_binary_is_an_error_not_a_pass(tmp_path):
    with pytest.raises(secrets.ScanError):
        secrets.scan(tmp_path, ["a.py"], binary="/nonexistent/gitleaks")
