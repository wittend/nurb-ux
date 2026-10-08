#!/usr/bin/env python3
"""Stage pinned corresponding OCCT/OCP sources, build patches and license notices.

The source payload accompanies Linux packages; no source-download step is needed
on end-user machines. Checksums pin immutable source commits and release assets.
"""
import argparse
import hashlib
import json
import re
import shutil
import tarfile
import urllib.request
from pathlib import Path

OCP_VERSION = "7.9.3.1.1"
OCCT_VERSION = "7.9.3"
SOURCES = [
    {
        "filename": "OCCT-7.9.3.tar.gz", "component": "Open CASCADE Technology",
        "version": OCCT_VERSION, "revision": "a016080bf6738d6aeae020badee4e888ad1540a5",
        "url": "https://codeload.github.com/Open-Cascade-SAS/OCCT/tar.gz/a016080bf6738d6aeae020badee4e888ad1540a5",
        "sha256": "c533f2667b59921bd6bd40ce82e7b9900b0289ccc731af5fdeeba097de80ef0f",
        "notices": ["LICENSE_LGPL_21.txt", "OCCT_LGPL_EXCEPTION.txt"],
    },
    {
        "filename": "OCP-7.9.3.1.1.tar.gz", "component": "CadQuery OCP bindings",
        "version": OCP_VERSION, "revision": "d69b064a3a604ebf245b1f3b14fb54c835a3a571",
        "url": "https://codeload.github.com/CadQuery/OCP/tar.gz/d69b064a3a604ebf245b1f3b14fb54c835a3a571",
        "sha256": "a5153cef9f4a3a3dbbb1d498a971206a6c35dc4d829e7e011f96e0539c22e616",
        "notices": ["LICENSE"],
    },
    {
        "filename": "ocp-build-system-7.9.3.1.1.tar.gz", "component": "OCP wheel build scripts and OCCT patches",
        "version": OCP_VERSION, "revision": "df2c31c25b8fce57c497895aa514e9c3550c9f02",
        "url": "https://codeload.github.com/CadQuery/ocp-build-system/tar.gz/df2c31c25b8fce57c497895aa514e9c3550c9f02",
        "sha256": "b2a5330ae62d82269d9c9a5d25a21cf185bd2ae2c7716e461dde297e03c56aa2",
        "notices": ["LICENSE"],
    },
    {
        "filename": "OCP_src_stubs_Linux-7.9.3.1.1.zip", "component": "Generated OCP Linux binding C++ sources and stubs",
        "version": OCP_VERSION, "revision": "7.9.3.1.1 Linux release asset",
        "url": "https://github.com/CadQuery/OCP/releases/download/7.9.3.1.1/OCP_src_stubs_Linux.zip",
        "sha256": "2c5ecdb81bd74a96c024fbf148dd14b9367884063c37461b543f89f8d69ac00e",
        "notices": [],
    },
]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage(resources, cache=None):
    lock = (resources / "requirements.lock").read_text()
    pin = re.search(r"(?m)^cadquery-ocp-novtk==([^\s\\]+)", lock)
    if not pin or pin.group(1) != OCP_VERSION:
        raise RuntimeError("Update corresponding source pins when the OCP dependency changes")
    destination = resources / "python-sources"
    destination.mkdir(parents=True, exist_ok=True)
    notices = resources / "python-notices" / "occt-ocp-sources"
    notices.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        target = destination / source["filename"]
        if not target.exists() or sha256(target) != source["sha256"]:
            cached = cache / source["filename"] if cache else None
            temporary = target.with_suffix(target.suffix + ".partial")
            try:
                if cached and cached.is_file() and sha256(cached) == source["sha256"]:
                    shutil.copyfile(cached, temporary)
                else:
                    print(f"stage: downloading corresponding source {source['filename']}", flush=True)
                    request = urllib.request.Request(source["url"], headers={"User-Agent": "nurb-ux-source-stager"})
                    with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as output:
                        shutil.copyfileobj(response, output)
                if sha256(temporary) != source["sha256"]:
                    raise RuntimeError(f"Source checksum mismatch: {source['filename']}")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        if source["notices"]:
            with tarfile.open(target) as archive:
                root = archive.getnames()[0].split("/")[0]
                component = notices / source["filename"].removesuffix(".tar.gz")
                component.mkdir(exist_ok=True)
                for name in source["notices"]:
                    member = archive.extractfile(f"{root}/{name}")
                    if member is None:
                        raise RuntimeError(f"Missing source license: {name}")
                    (component / name).write_bytes(member.read())
    readme = """Corresponding source for bundled CAD native libraries
====================================================

This directory travels with the Linux installer for both amd64 and arm64.
OCCT 7.9.3 is distributed under LGPL 2.1 with its OCCT additional exception.
CadQuery OCP bindings and the wheel build system retain their included licenses.
Verbatim licenses are also copied to ../python-notices/occt-ocp-sources/.
Source checksums, revisions and original URLs are in source-manifest.json.

Build and modification instructions
----------------------------------
Extract OCCT-7.9.3.tar.gz and ocp-build-system-7.9.3.1.1.tar.gz.
The build system includes .github/workflows/build-ocp.yml, environment.yml,
.github/actions/build-sdks/action.yml and build-ocp/action.yml. Those scripts
specify the toolchain, Python versions, native dependencies, compiler flags,
CMake settings and wheel repair. Apply patches/occt-7.9.3/
switch-vtk-freetype-cmake-order.patch to the OCCT source as the build action
instructs. Select use-vtk=novtk and Python 3.13 on the target architecture.
Use OCP_src_stubs_Linux-7.9.3.1.1.zip for the generated C++ bindings consumed
by the build; OCP-7.9.3.1.1.tar.gz also includes the binding project sources.
The generated binding archive is the exact upstream Linux release asset used
by the pinned build system. The build system archive contains all bundled
OCCT patches and installation scripts; no local CAD library patches were added.
Build prerequisites may require downloads when rebuilding source.

Replacing the shared libraries
-----------------------------
The installed application uses ordinary dynamically linked OCP/OCCT libraries
in its writable per-user Python environment. Build a compatible modified
cadquery-ocp-novtk wheel for Python 3.13 and the installed architecture, then
install it with the bundled nurb-uv executable using:

  nurb-uv pip install --offline --no-deps --reinstall \\
    --python "$APP_DATA/env/bin/python" /path/to/modified/cadquery_ocp_novtk-*.whl

APP_DATA is the application's data directory, normally
${XDG_DATA_HOME:-$HOME/.local/share}/dev.nurb.desktop on Linux. Check the installed
application identifier if its folder differs. Keep the matching wheel and a
backup: an application upgrade or Repair environment may recreate the venv.
For unpackaged builds uv can be used in place of nurb-uv. No library signatures
or integrity checks prevent users from replacing installed shared libraries;
bundle checks verify distribution input archives, not the user's installed
libraries. Reverse engineering for debugging modifications to LGPL libraries
is permitted under their license terms. Preserve upstream notices when
redistributing modified versions.
"""
    (destination / "README.txt").write_text(readme)
    manifest = {
        "schema": 1, "ocp_version": OCP_VERSION, "occt_version": OCCT_VERSION,
        "sources": [{k: v for k, v in source.items() if k != "notices"} for source in SOURCES],
    }
    (destination / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("stage: verified corresponding OCCT/OCP sources and licenses")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    stage(args.resources.resolve(), args.cache.resolve() if args.cache else None)
