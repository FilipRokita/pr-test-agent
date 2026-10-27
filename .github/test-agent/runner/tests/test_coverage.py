import subprocess

import pytest

from test_agent import coverage

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**ENV, "HOME": str(cwd)}).stdout.strip()


COBERTURA = """<?xml version="1.0" ?>
<coverage version="7" timestamp="1" lines-valid="6" lines-covered="3" line-rate="0.5" branches-covered="0" branches-valid="0" branch-rate="0" complexity="0">
<sources><source>{source}</source></sources>
<packages><package name="app" line-rate="0.5" branch-rate="0" complexity="0"><classes>
<class name="x.py" filename="app/x.py" complexity="0" line-rate="0.5" branch-rate="0"><methods/><lines>
{lines}
</lines></class></classes></package></packages></coverage>"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "backend/app").mkdir(parents=True)
    (tmp_path / "backend/app/x.py").write_text("a = 1\nb = 2\nc = 3\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A"); _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "backend/app/x.py").write_text("a = 1\nb = 2\nc = 3\nd = 4\ne = 5\nf = 6\n")
    _git(tmp_path, "commit", "-qam", "change")
    return tmp_path, base


def test_backend_changed_lines_are_measured_from_the_cobertura_report(repo):
    root, base = repo
    lines = "\n".join(f'<line number="{n}" hits="{h}"/>' for n, h in [(1, 1), (2, 1), (3, 1), (4, 1), (5, 0), (6, 0)])
    report = root / "coverage.xml"
    report.write_text(COBERTURA.format(source=root / "backend", lines=lines))
    result = coverage.changed_lines(root, report, base)
    assert result["total"] == 3 and result["covered"] == 1
    assert result["percent"] == pytest.approx(33.3, abs=0.1)
    assert result["files"]["backend/app/x.py"]["uncovered"] == [5, 6]


def test_no_changed_executable_lines_is_reported_as_nothing_to_cover(repo):
    root, base = repo
    report = root / "coverage.xml"
    report.write_text(COBERTURA.format(source=root / "backend", lines='<line number="1" hits="1"/>'))
    result = coverage.changed_lines(root, report, base)
    assert result["total"] == 0 and result["percent"] is None


def test_the_frontend_lcov_report_is_rewritten_to_repository_paths():
    lcov = "TN:\nSF:src/lib/http.ts\nDA:1,1\nend_of_record\nSF:src/App.tsx\nDA:1,0\nend_of_record\n"
    rewritten = coverage.rewrite_lcov(lcov, "frontend")
    assert "SF:frontend/src/lib/http.ts" in rewritten and "SF:frontend/src/App.tsx" in rewritten
    assert "SF:src/" not in rewritten


def test_frontend_changed_lines_are_measured_from_lcov(repo):
    root, base = repo
    (root / "frontend/src/lib").mkdir(parents=True)
    (root / "frontend/src/lib/a.ts").write_text("one\ntwo\n")
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "frontend base")
    base = _git(root, "rev-parse", "HEAD")
    (root / "frontend/src/lib/a.ts").write_text("one\ntwo\nthree\nfour\n")
    _git(root, "commit", "-qam", "frontend change")
    report = root / "lcov.info"
    report.write_text("TN:\nSF:src/lib/a.ts\nDA:1,1\nDA:2,1\nDA:3,1\nDA:4,0\nend_of_record\n")
    result = coverage.changed_lines(root, report, base, stack="frontend")
    assert result["total"] == 2 and result["covered"] == 1
    assert result["files"]["frontend/src/lib/a.ts"]["uncovered"] == [4]
