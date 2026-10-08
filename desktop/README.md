# nurb-ux desktop

A Tauri shell around nurb: project rail, agent chat, and live viewer in one window.

## Linux packages

This fork builds native **amd64 (x86_64)** and **arm64 (aarch64)** packages. In GitHub Actions, run **Fork Linux packages** against the desired fork branch. Download `nurb-ux-linux-amd64` or `nurb-ux-linux-arm64` from the completed run. Each artifact contains a `.deb`, `.rpm`, and AppImage. The workflow has read-only repository permissions and does not publish to PyPI, create releases, upload to upstream, or require signing secrets.

Both amd64 and arm64 use Ubuntu 22.04 as their build baseline (glibc 2.35). Every package format requires a compatible system glibc; choosing a `.deb` or `.rpm` does not lower that requirement. Debian 12/13 and Ubuntu 22.04/24.04 are candidates for both architectures. These baselines describe the build environment, not compatibility verified on those distributions. Prefer the `.deb` on Debian and Ubuntu, where APT installs the declared desktop libraries and bubblewrap. See the root README for installation commands. Both architectures are built natively, rather than cross-compiling CAD libraries.

Linux packages bundle standalone Python 3.13, this checkout's nurb wheel, the CAD dependency wheel set, and uv. First launch creates the local Python environment from those files without network access. Node and AI adapters remain optional downloads; provider authentication and AI requests need internet access. Modelling, viewing, checks, and exports run locally.

Automatic updates are disabled in this fork. Install newer fork packages manually. The inherited upstream publish workflows are guarded to run only in the upstream repository; use the manual fork workflow here.

## Development and local builds

Install Node 22+, Rust, uv, and the Linux Tauri development libraries:

```sh
sudo apt-get install build-essential libwebkit2gtk-4.1-dev libxdo-dev \
  libayatana-appindicator3-dev librsvg2-dev libssl-dev libdbus-1-dev \
  patchelf pkg-config bubblewrap curl xz-utils
cd desktop
npm ci
npm run tauri dev
```

Debug builds use the checkout and development tools on PATH. `npm run stage` prepares package resources; building on Linux downloads the architecture's portable Python and wheels at build time. Build native packages on each architecture with:

```sh
npm run tauri build -- --bundles deb,rpm,appimage --config '{"bundle":{"createUpdaterArtifacts":false}}'
```

Packages appear under `src-tauri/target/release/bundle/`. No updater signing key is needed for this command.

## Bundled libraries and sources

OCCT is distributed through the OCP wheel as separate dynamically linked libraries. The app includes LGPL-2.1 and the Open CASCADE exception in About. Installed libraries remain in the app data environment, where they can be inspected or replaced. Package resources retain Python runtime notices and wheel license metadata. The generated bundle manifest records the exact runtime and dependency files used by each architecture. Package resources also include the corresponding OCCT and OCP source archives, their build scripts and patches, and a source manifest under `python-sources/`.

OCCT sources: <https://github.com/Open-Cascade-SAS/OCCT>. OCP sources and build tooling: <https://github.com/CadQuery/OCP>. Standalone Python sources and build tooling: <https://github.com/astral-sh/python-build-standalone>. Use the exact versions recorded by the bundle manifest when rebuilding or obtaining corresponding sources. Redistribution requires retaining the applicable licenses, notices, and corresponding sources for the shipped libraries; links alone do not replace those obligations.

To rebuild with a replacement CAD dependency, change the dependency constraints in the root `pyproject.toml`, update `uv.lock` with `uv lock`, restage on the target architecture, and rebuild the package. If the OCP version changes, update the matching source revisions and checksums in `scripts/stage-sources.py`; staging refuses to pair a new OCP wheel with old sources. For an installed environment, replace the wheel/library in that environment using its Python interpreter and an appropriate compatible wheel.
