import json
import subprocess
import sys
from pathlib import Path

from skipwatch.models import SCHEMA_MODELS

ROOT = Path(__file__).resolve().parents[2]


def test_r_arch_2_every_model_has_committed_schema():
    for key, model in SCHEMA_MODELS.items():
        path = ROOT / "schemas" / f"{key}.schema.json"
        assert path.exists(), f"missing {path}"
        assert json.loads(path.read_text()) == model.model_json_schema(by_alias=True)


def test_export_schemas_check_detects_stale(tmp_path):
    out = tmp_path / "schemas"
    out.mkdir()
    (out / "ingest.schema.json").write_text("{}")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_schemas.py"), "--check", "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1 and "ingest.schema.json" in r.stdout
