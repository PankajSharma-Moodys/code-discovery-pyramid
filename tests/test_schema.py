import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "result.schema.json"
FIXTURE = ROOT / "tests" / "fixtures" / "python"


def _run_scan() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "code_scanner.cli", "scan", str(FIXTURE), "--out", "-"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


def test_scan_output_validates_against_schema():
    schema = json.loads(SCHEMA_PATH.read_text())
    result = _run_scan()
    jsonschema.validate(result, schema)


def test_scan_finds_the_fixture_file():
    result = _run_scan()
    paths = [f["path"] for f in result["files"]]
    assert "sample.py" in paths


def test_config_digest_is_deterministic():
    result = _run_scan()
    assert len(result["scan"]["config_digest"]) == 64
