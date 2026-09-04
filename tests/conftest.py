import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def multimodule_repo(tmp_path: Path) -> Path:
    """A git-initialized copy of tests/fixtures/multimodule.

    The fixture is checked in as a plain directory (not a real git repo, to avoid
    nesting a .git inside the code-scanner repo itself) and turned into one here,
    which also exercises the nested-.gitignore path RESEARCH §4 cares about.
    """
    src = Path(__file__).parent / "fixtures" / "multimodule"
    dest = tmp_path / "multimodule"
    shutil.copytree(src, dest)
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=dest, check=True,
    )
    return dest
