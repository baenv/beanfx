"""pytest front end for the test scripts in this folder. Each test_*.py stays a plain script (run it alone with
python, exit 0 when clean); pytest runs each one in process as one test, so a run gives one report and pytest-cov
measures the kit and gate.py. test_*.mjs runs under node, skipped when node is missing.

    pip install pytest pytest-cov
    pytest                                   # from the repo root (pyproject.toml points here)
    pytest --cov --cov-report=term-missing   # with coverage of kit/ and gate.py
"""
import runpy
import shutil
import subprocess
import sys

import pytest


class ScriptFailed(Exception):
    pass


class Script(pytest.File):
    def collect(self):
        yield ScriptItem.from_parent(self, name=self.path.stem)


class ScriptItem(pytest.Item):
    def runtest(self):
        path = str(self.path)
        if self.path.suffix == ".mjs":
            node = shutil.which("node")
            if not node:
                pytest.skip("node is not installed")
            run = subprocess.run([node, path], capture_output=True, text=True)
            print(run.stdout + run.stderr)
            code = run.returncode
        else:
            argv, mods = sys.argv, sys.path[:]
            sys.argv = [path]
            try:
                runpy.run_path(path, run_name="__main__")
                code = 0
            except SystemExit as e:
                code = e.code
            finally:
                sys.argv, sys.path[:] = argv, mods
        if code not in (0, None):
            raise ScriptFailed(f"{self.path.name} exited {code}; its FAIL lines are in the captured output below")

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, ScriptFailed):
            return str(excinfo.value)
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.path, 0, self.name


def pytest_collect_file(file_path, parent):
    if file_path.name.startswith("test_") and file_path.suffix in (".py", ".mjs"):
        return Script.from_parent(parent, path=file_path)
