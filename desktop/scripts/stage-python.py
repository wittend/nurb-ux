#!/usr/bin/env python3
"""Stage a native Linux Python distribution and an offline, hash-locked wheelhouse.

Run only on the target architecture. Generated payloads live in ignored resources.
The build needs network access; first-launch CAD provisioning does not.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

PYTHON_VERSION = "3.13.7"
PIP_VERSION = "25.3"
ARCHITECTURES = {"x86_64": "amd64", "aarch64": "arm64"}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_manifest(resources, architecture):
    wheels = sorted((resources / "wheelhouse").glob("*.whl"))
    if not wheels:
        raise RuntimeError("No wheels were staged")
    manifest = {
        "schema": 1, "platform": "linux", "architecture": architecture,
        "python_version": PYTHON_VERSION,
        "archive_sha256": sha256(resources / "python-runtime.tar.gz"),
        "requirements_sha256": sha256(resources / "requirements.lock"),
        "wheels": [{"filename": p.name, "sha256": sha256(p)} for p in wheels],
        "stager_sha256": sha256(__file__),
    }
    (resources / "python-bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")


def collect_notices(resources):
    destination = resources / "python-notices"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir()
    for wheel in sorted((resources / "wheelhouse").glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                parts = Path(name).parts
                if not parts or ".." in parts or name.startswith("/"):
                    continue
                if ".dist-info/" in name and (
                    name.endswith("/METADATA") or any(
                        word in name.lower() for word in ("license", "copying", "notice")
                    )
                ) and not name.endswith("/"):
                    target = destination / wheel.stem / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
    (destination / "README.txt").write_text(
        "Python dependency metadata and license notices copied verbatim from bundled wheels.\n"
        "Portable CPython retains its license files inside python-runtime.tar.gz.\n"
        "Open CASCADE source: https://github.com/Open-Cascade-SAS/OCCT\n"
        "OCP binding source: https://github.com/CadQuery/OCP\n"
        "See the packaged third-party notice for redistribution and replacement instructions.\n"
    )


def stage(repo, resources):
    if platform.system() != "Linux" or platform.machine() not in ARCHITECTURES:
        raise RuntimeError("Python bundles require a native Linux amd64 or arm64 build host")
    manifest_path = resources / "python-bundle.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        local_wheels = list(resources.glob("nurb-*.whl"))
        expected = {entry["filename"]: entry["sha256"] for entry in manifest["wheels"]}
        if (manifest.get("stager_sha256") == sha256(__file__)
            and manifest.get("architecture") == ARCHITECTURES[platform.machine()]
            and manifest["requirements_sha256"] == sha256(resources / "requirements.lock")
            and manifest["archive_sha256"] == sha256(resources / "python-runtime.tar.gz")
            and len(local_wheels) == 1
            and expected.get(local_wheels[0].name) == sha256(local_wheels[0])
            and all((resources / "wheelhouse" / name).is_file() and
                    sha256(resources / "wheelhouse" / name) == digest
                    for name, digest in expected.items())):
            print("stage: reusing verified native Python/CAD payload")
            return
    def run(*args):
        subprocess.run(args, check=True, cwd=repo)
    with tempfile.TemporaryDirectory(prefix="nurb-python-") as temporary:
        temporary = Path(temporary)
        install = temporary / "managed"
        run("uv", "python", "install", PYTHON_VERSION, "--install-dir", str(install), "--no-bin")
        interpreters = sorted({p.resolve() for p in install.glob("cpython-*/bin/python3.13")})
        if len(interpreters) != 1:
            raise RuntimeError("Expected exactly one portable Python interpreter")
        runtime = interpreters[0].parent.parent
        (runtime / "bin/python3").symlink_to("python3.13") if not (runtime / "bin/python3").exists() else None
        # Retain the complete relocatable distribution, including standard library,
        # native libraries and CPython's license. Do not archive uv's install links.
        with tarfile.open(resources / "python-runtime.tar.gz", "w:gz") as archive:
            archive.add(runtime, arcname="python")
        wheels = resources / "wheelhouse"
        if wheels.exists():
            shutil.rmtree(wheels)
        wheels.mkdir()
        for wheel in resources.glob("nurb-*.whl"):
            shutil.copy2(wheel, wheels / wheel.name)
        downloader = temporary / "downloader"
        run("uv", "venv", "--python", str(interpreters[0]), str(downloader))
        run("uv", "pip", "install", "--python", str(downloader / "bin/python"), f"pip=={PIP_VERSION}")
        run(str(downloader / "bin/python"), "-m", "pip", "download", "--require-hashes",
            "--only-binary=:all:", "--no-deps", "-r", str(resources / "requirements.lock"),
            "--dest", str(wheels))
        # Verify the actual payload after relocating the runtime. All dependencies
        # must install offline, including native OCP; no source builds are allowed.
        relocated = temporary / "relocated"
        relocated.mkdir()
        with tarfile.open(resources / "python-runtime.tar.gz") as archive:
            archive.extractall(relocated, filter="data")
        checkenv = temporary / "verify"
        def run_offline(*args):
            environment = dict(os.environ, UV_CACHE_DIR=str(temporary / "empty-cache"),
                               UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never")
            subprocess.run(args, check=True, cwd=repo, env=environment)
        run_offline("uv", "venv", "--offline", "--python", str(relocated / "python/bin/python3"), str(checkenv))
        run_offline("uv", "pip", "install", "--offline", "--no-index", "--find-links", str(wheels),
            "--require-hashes", "--python", str(checkenv / "bin/python"),
            "-r", str(resources / "requirements.lock"))
        local_wheel = next(wheels.glob("nurb-*.whl"))
        run_offline("uv", "pip", "install", "--offline", "--no-index", "--no-deps", "--python",
            str(checkenv / "bin/python"), str(local_wheel))
        run(str(checkenv / "bin/python"), "-c",
            "import build123d, trimesh, watchdog, websockets, nurb; "
            "from build123d import Box; assert abs(Box(1, 2, 3).volume - 6) < 1e-6")
    collect_notices(resources)
    write_manifest(resources, ARCHITECTURES[platform.machine()])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    args = parser.parse_args()
    stage(args.repo.resolve(), args.resources.resolve())
