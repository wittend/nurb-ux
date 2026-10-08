"""Artifact integrity and redistribution notices for the Linux Python bundle."""
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

MODULE = Path(__file__).parents[1] / "desktop/scripts/stage-python.py"
spec = importlib.util.spec_from_file_location("stage_python", MODULE)
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


def test_manifest_hashes_every_offline_artifact(tmp_path):
    (tmp_path / "wheelhouse").mkdir()
    wheel = tmp_path / "wheelhouse/nurb-0.26.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel content")
    (tmp_path / "python-runtime.tar.gz").write_bytes(b"runtime content")
    (tmp_path / "requirements.lock").write_bytes(b"locked requirements")
    staging.write_manifest(tmp_path, "arm64")
    manifest = json.loads((tmp_path / "python-bundle.json").read_text())
    assert manifest["architecture"] == "arm64"
    assert manifest["archive_sha256"] == hashlib.sha256(b"runtime content").hexdigest()
    assert manifest["requirements_sha256"] == hashlib.sha256(b"locked requirements").hexdigest()
    assert manifest["wheels"] == [{"filename": wheel.name,
                                  "sha256": hashlib.sha256(b"wheel content").hexdigest()}]


def test_notices_preserves_license_metadata_and_blocks_traversal(tmp_path):
    (tmp_path / "wheelhouse").mkdir()
    with zipfile.ZipFile(tmp_path / "wheelhouse/example-1-py3-none-any.whl", "w") as wheel:
        wheel.writestr("example-1.dist-info/licenses/LICENSE", "license terms")
        wheel.writestr("example-1.dist-info/METADATA", "License-Expression: MIT")
        wheel.writestr("example/module.py", "code")
        wheel.writestr("../../example-1.dist-info/LICENSE", "unsafe")
    staging.collect_notices(tmp_path)
    texts = [p.read_text() for p in (tmp_path / "python-notices").rglob("*") if p.is_file()]
    assert "license terms" in texts
    assert "License-Expression: MIT" in texts
    assert "code" not in texts
    assert "unsafe" not in texts
