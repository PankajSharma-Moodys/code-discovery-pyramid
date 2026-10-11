import os
from unittest import mock


def use_home(testcase, path) -> None:
    """Point this process's `CDP_HOME` at `path` for the test; the web API only
    serves the one `CDP_HOME` store (a request cannot choose another)."""
    patcher = mock.patch.dict(os.environ, {"CDP_HOME": str(path)})
    patcher.start()
    testcase.addCleanup(patcher.stop)
