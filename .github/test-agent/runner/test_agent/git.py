"""Run git without trusting the repository's own configuration.

Test code that ran with write access to `.git` could plant `core.fsmonitor`, hooks or `diff.external`, and the
next git call in a process that holds a secret would execute them. Every git call made by the runner therefore
overrides those settings and never uses system or global configuration.
"""

import os
import subprocess
from pathlib import Path

_HARDENING = (
    "-c", "core.fsmonitor=",
    "-c", "core.hooksPath=/dev/null",
    "-c", "protocol.ext.allow=never",
    "-c", "safe.directory=*",
)


class GitError(RuntimeError):
    pass


def run(cwd: Path | str, *args: str, check: bool = True, stdin: str | None = None,
        config: tuple[tuple[str, str], ...] = (), extra_env: dict | None = None) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        **(extra_env or {}),
    }
    options = [part for key, value in config for part in ("-c", f"{key}={value}")]
    proc = subprocess.run(
        ["git", *_HARDENING, *options, *args], cwd=cwd, env=env, input=stdin,
        capture_output=True, text=True, check=False,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout
