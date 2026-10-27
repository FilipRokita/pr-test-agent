"""Run model-written tests where they cannot reach secrets, the network, or the repository itself.

The tests run as an unprivileged user (uid 65534) with an empty environment, no network, their own PID
namespace, no new privileges and no capabilities. The workspace is read-only for that user and `.git` is not
accessible at all; results go to a fresh output directory outside the workspace.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

SANDBOX_UID = 65534
BASE_PATH = ["/usr/bin", "/bin"]


def build_command(argv, *, out_dir, path_dirs, use_sudo, extra_env=None) -> list[str]:
    env = {
        "PATH": ":".join([*path_dirs, *BASE_PATH]),
        "HOME": str(out_dir),
        "CI": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "COVERAGE_FILE": str(Path(out_dir) / ".coverage"),
        **(extra_env or {}),
    }
    prefix = ["sudo", "-n"] if use_sudo else []
    return [
        *prefix,
        "unshare", "--net", "--pid", "--fork", "--kill-child", "--",
        "setpriv", f"--reuid={SANDBOX_UID}", f"--regid={SANDBOX_UID}", "--clear-groups",
        "--no-new-privs", "--inh-caps=-all", "--bounding-set=-all",
        "env", "-i", *[f"{key}={value}" for key, value in env.items()],
        *argv,
    ]


def _privileged(cmd: list[str]) -> list[str]:
    return cmd if os.geteuid() == 0 else ["sudo", "-n", *cmd]


def make_traversable(path: Path | str) -> None:
    """Let the sandbox user walk down to `path`: execute permission on every parent directory."""
    use_acl = shutil.which("setfacl") is not None
    resolved = Path(path).resolve()
    for parent in reversed([resolved, *resolved.parents]):
        if str(parent) == "/":
            continue
        if use_acl:
            cmd = ["setfacl", "-m", f"u:{SANDBOX_UID}:x", str(parent)]
        else:
            cmd = ["chmod", "o+x", str(parent)]
        subprocess.run(_privileged(cmd), check=True, capture_output=True)


def prepare_out_dir(out_dir: Path | str) -> Path:
    """Create an empty output directory owned by the sandbox user."""
    out = Path(out_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    make_traversable(out.parent)
    if out.exists():
        subprocess.run(_privileged(["rm", "-rf", str(out)]), check=True)
    out.mkdir(parents=True)
    subprocess.run(_privileged(["chown", "-R", f"{SANDBOX_UID}:{SANDBOX_UID}", str(out)]), check=True)
    # The runner reads results back, so others must be able to traverse and read.
    subprocess.run(_privileged(["chmod", "755", str(out)]), check=True)
    return out


def run(argv, *, cwd, out_dir, path_dirs, timeout=300, extra_env=None) -> subprocess.CompletedProcess:
    cmd = build_command(argv, out_dir=out_dir, path_dirs=path_dirs, use_sudo=os.geteuid() != 0, extra_env=extra_env)
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
    finally:
        # Belt and braces: the PID namespace already ends everything the call started.
        if shutil.which("pkill"):
            subprocess.run(_privileged(["pkill", "-u", str(SANDBOX_UID)]), capture_output=True, check=False)


def read_output(out_dir: Path | str, name: str, max_bytes: int = 5_000_000) -> str | None:
    """Read a result file written by sandboxed code. It is untrusted: no symlinks, no huge files."""
    path = Path(out_dir) / name
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
        return None
    return path.read_text(errors="replace")
