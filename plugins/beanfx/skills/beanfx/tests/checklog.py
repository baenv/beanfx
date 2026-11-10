"""Every check a test script makes, pass or fail, in run order. conftest.py turns each record into its own pytest
test, so a failing run names the check, not just the file. A script run alone with python ignores it.

    import checklog
    def ok(cond, msg):
        checklog.record(cond, msg)
        ...
"""
RESULTS = []


def record(cond, msg):
    RESULTS.append((str(msg), bool(cond)))
    return bool(cond)


def reset():
    RESULTS.clear()
