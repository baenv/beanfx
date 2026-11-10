"""pytest front end for the test scripts in this folder. Each test_*.py stays a plain script (run it alone with
python, exit 0 when clean). Here it runs once, in process at collection, and every check it records through
checklog.py becomes its own test, so a failure names the check; pytest-cov measures the kit and gate.py on the way.
test_*.mjs does the same through `CHECK ok|fail <name>` lines (BEANFX_CHECKS=1), skipped when node is missing. A
script that records nothing (test_preview.py), crashes, or exits non-zero with every check passing shows as one
test named after the script.

    pip install pytest pytest-cov
    pytest                                   # from the repo root (pyproject.toml points here)
    pytest --cov --cov-report=term-missing   # with coverage of kit/ and gate.py; fails under fail_under
"""
import contextlib
import io
import os
import re
import runpy
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import checklog  # noqa: E402

CHECK = re.compile(r"^CHECK (ok|fail) (.*)$")


class CheckFailed(Exception):
    pass


def run_python(path):
    """Runs the script in this process; returns (exit code, output, records)."""
    checklog.reset()
    argv, saved_path, out = sys.argv, sys.path[:], io.StringIO()
    sys.argv = [str(path)]
    sys.path.insert(0, str(path.parent))
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            runpy.run_path(str(path), run_name="__main__")
    except SystemExit as e:
        code = e.code or 0
    except Exception:  # a crash is reported as the script's own test
        out.write(traceback.format_exc())
        code = "crash"
    finally:
        sys.argv, sys.path[:] = argv, saved_path
    return code, out.getvalue(), list(checklog.RESULTS)


def run_node(path):
    node = shutil.which("node")
    if not node:
        return None, "node is not installed", []
    run = subprocess.run([node, str(path)], capture_output=True, text=True, env=dict(os.environ, BEANFX_CHECKS="1"))
    records, rest = [], []
    for line in (run.stdout + run.stderr).splitlines():
        m = CHECK.match(line)
        if m:
            records.append((m[2], m[1] == "ok"))
        else:
            rest.append(line)
    return run.returncode, "\n".join(rest), records


def names(records):
    """Unique, readable test ids: whitespace collapsed, long names cut, repeats numbered."""
    seen, out = {}, []
    for msg, _ in records:
        n = " ".join(msg.split())
        n = n if len(n) <= 90 else n[:87] + "..."
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n} [{seen[n]}]")
    return out


class Script(pytest.File):
    def collect(self):
        code, output, records = (run_node if self.path.suffix == ".mjs" else run_python)(self.path)
        if code is None:
            yield Result.from_parent(self, name=self.path.stem, passed=None, detail=output)
            return
        for name, (msg, passed) in zip(names(records), records):
            yield Result.from_parent(self, name=name, passed=passed, detail=msg)
        # the script's own test: when no check speaks for it (nothing recorded, a crash, or a bad exit with
        # every recorded check passing)
        if not records or code == "crash" or (code not in (0, None) and all(p for _, p in records)):
            why = "crashed" if code == "crash" else f"exited {code}"
            yield Result.from_parent(self, name=self.path.stem, passed=code in (0, None),
                                     detail=f"{self.path.name} {why}\n{output}")


class Result(pytest.Item):
    def __init__(self, *, passed, detail, **kw):
        super().__init__(**kw)
        self.passed, self.detail = passed, detail

    def runtest(self):
        if self.passed is None:
            pytest.skip(self.detail)
        if not self.passed:
            raise CheckFailed(self.detail)

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, CheckFailed):
            return f"FAIL {excinfo.value}"
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.path, 0, self.name


def pytest_collect_file(file_path, parent):
    if file_path.name.startswith("test_") and file_path.suffix in (".py", ".mjs"):
        return Script.from_parent(parent, path=file_path)
