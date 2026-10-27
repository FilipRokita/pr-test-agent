import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from test_agent import sandbox


def test_command_drops_privileges_and_the_environment(tmp_path):
    cmd = sandbox.build_command(
        ["python", "-m", "pytest"], out_dir=tmp_path, path_dirs=["/opt/py/bin", "/opt/node/bin"], use_sudo=False,
    )
    joined = " ".join(cmd)
    for required in ("unshare", "--net", "--pid", "--kill-child", "--reuid=65534", "--no-new-privs",
                     "--inh-caps=-all", "--bounding-set=-all", "env -i"):
        assert required in joined
    assert "PATH=/opt/py/bin:/opt/node/bin:/usr/bin:/bin" in joined
    assert cmd[-3:] == ["python", "-m", "pytest"]


def test_sudo_is_added_only_when_requested(tmp_path):
    assert sandbox.build_command(["true"], out_dir=tmp_path, path_dirs=[], use_sudo=False)[0] == "unshare"
    assert sandbox.build_command(["true"], out_dir=tmp_path, path_dirs=[], use_sudo=True)[:2] == ["sudo", "-n"]


def test_temporary_files_go_to_the_output_directory(tmp_path):
    cmd = sandbox.build_command(["true"], out_dir=tmp_path, path_dirs=[], use_sudo=False)
    assert f"TMPDIR={tmp_path}/tmp" in cmd


def test_inherited_environment_is_never_forwarded(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "super-secret-value")
    cmd = sandbox.build_command(["true"], out_dir=tmp_path, path_dirs=[], use_sudo=False)
    assert "super-secret-value" not in " ".join(cmd)


def test_read_output_returns_regular_files(tmp_path):
    (tmp_path / "junit.xml").write_text("<ok/>")
    assert sandbox.read_output(tmp_path, "junit.xml") == "<ok/>"


def test_read_output_ignores_symlinks_and_missing_files(tmp_path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("do not read")
    (tmp_path / "junit.xml").symlink_to(secret)
    assert sandbox.read_output(tmp_path, "junit.xml") is None
    assert sandbox.read_output(tmp_path, "absent.xml") is None


def test_read_output_caps_the_size(tmp_path):
    (tmp_path / "big.xml").write_text("x" * 5000)
    assert sandbox.read_output(tmp_path, "big.xml", max_bytes=1000) is None


def _can_sandbox() -> bool:
    if shutil.which("unshare") is None or shutil.which("setpriv") is None:
        return False
    probe = sandbox.build_command(["true"], out_dir=Path(tempfile.gettempdir()), path_dirs=[], use_sudo=os.geteuid() != 0)
    return subprocess.run(probe, capture_output=True).returncode == 0


needs_sandbox = pytest.mark.skipif(not _can_sandbox(), reason="needs unshare, setpriv and root or passwordless sudo")


@pytest.fixture
def workspace():
    """A read-only workspace the unprivileged user can traverse, with a fake .git and an output directory."""
    base = Path(tempfile.mkdtemp(prefix="sbx-test-"))
    base.chmod(0o755)
    ws = base / "ws"
    (ws / ".git").mkdir(parents=True)
    (ws / ".git" / "config").write_text("[core]\n")
    (ws / ".git").chmod(0o700)
    (ws / "a.txt").write_text("source\n")
    ws.chmod(0o755)
    out = base / "out"
    sandbox.prepare_out_dir(out)
    yield ws, out
    subprocess.run(["rm", "-rf", str(base)], check=False)
    subprocess.run(["sudo", "-n", "rm", "-rf", str(base)], check=False, capture_output=True)


def _run(ws, out, script, **env):
    cmd = sandbox.build_command(["sh", "-c", script], out_dir=out, path_dirs=[], use_sudo=os.geteuid() != 0)
    return subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=60,
                          env={**os.environ, **env})


@needs_sandbox
def test_code_in_the_sandbox_runs_as_an_unprivileged_user(workspace):
    ws, out = workspace
    assert _run(ws, out, "id -u").stdout.strip() == "65534"


@needs_sandbox
def test_secrets_in_the_parent_environment_are_invisible(workspace):
    ws, out = workspace
    result = _run(ws, out, 'echo "[${CLAUDE_CODE_OAUTH_TOKEN:-absent}]"', CLAUDE_CODE_OAUTH_TOKEN="leaky-token")
    assert result.stdout.strip() == "[absent]"


@needs_sandbox
def test_the_workspace_cannot_be_modified(workspace):
    ws, out = workspace
    result = _run(ws, out, "touch new.txt; echo x > a.txt")
    assert result.returncode != 0
    assert not (ws / "new.txt").exists()
    assert (ws / "a.txt").read_text() == "source\n"


@needs_sandbox
def test_git_internals_cannot_be_read_or_changed(workspace):
    ws, out = workspace
    assert _run(ws, out, "cat .git/config").returncode != 0
    assert _run(ws, out, "echo '[core]\nfsmonitor = x' >> .git/config").returncode != 0
    assert (ws / ".git" / "config").read_text() == "[core]\n"


@needs_sandbox
def test_there_is_no_network(workspace):
    ws, out = workspace
    script = "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 53), timeout=3)\""
    assert _run(ws, out, script).returncode != 0


@needs_sandbox
def test_other_processes_environments_are_not_readable(workspace):
    ws, out = workspace
    assert _run(ws, out, "cat /proc/1/environ").returncode != 0


@needs_sandbox
def test_output_can_only_go_to_the_output_directory(workspace):
    ws, out = workspace
    assert _run(ws, out, f"echo ok > {out}/junit.xml").returncode == 0
    assert sandbox.read_output(out, "junit.xml").strip() == "ok"


@needs_sandbox
def test_background_processes_do_not_outlive_the_call(workspace):
    ws, out = workspace
    marker = out / "late.txt"
    _run(ws, out, f"(sleep 2; echo late > {marker}) &")
    import time
    time.sleep(3)
    assert not marker.exists()


@needs_sandbox
def test_a_tree_the_sandbox_wrote_into_can_be_removed_by_the_runner(workspace):
    ws, out = workspace
    _run(ws, out, f"mkdir -p {out}/tmp/deep && echo x > {out}/tmp/deep/file && chmod 500 {out}/tmp/deep")
    sandbox.remove_tree(out)
    assert not out.exists()
