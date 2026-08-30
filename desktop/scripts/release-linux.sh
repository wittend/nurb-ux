#!/bin/bash
set -euo pipefail

# Releases the Linux desktop packages: a .deb, an .rpm and an AppImage, each
# signed so installed copies can update themselves to it.
#
# The companion to release.sh, which does the same for macOS. They cannot be
# one script because Tauri links against the host's system webview, so each
# platform builds on its own machine. Both upload into the vX.Y.Z release that
# publish.yml creates from the merged version bump, and both merge their own
# half into one latest.json through feed.py rather than overwriting it.
#
# Ordering does not matter. Run this before or after the Mac; whichever goes
# second picks up the other's entries. What does matter is that both run for
# the same version, because feed.py drops entries from an older one.
#
# GitHub Actions runs this for both architectures once publish.yml has made the
# release, in .github/workflows/desktop-linux.yml. It still runs by hand on any
# Linux machine that has the updater key, which is how to repair a release.
#
# Credentials: only the updater signing key, from `tauri signer generate`.
# There is no Linux equivalent of notarization, so unlike the Mac script this
# needs no certificate and no App Store Connect key.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP="$SCRIPT_DIR/.."
cd "$DESKTOP"

# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

load_desktop_env
require_updater_key
derive_version

# bubblewrap is what confines every agent adapter, and both packages declare it
# as a dependency. Building without it installed still produces a package, but
# it means this machine has never run the sandboxed path it is shipping.
if ! command -v bwrap >/dev/null 2>&1; then
  echo "⚠️  bubblewrap is not installed here, so the sandbox has not been exercised."
  echo "   apt install bubblewrap, then run the Rust tests before releasing."
fi

# tauri-bundler names the packages with different words for the same machine:
# the .deb follows Debian (arm64) while the .rpm and the AppImage follow uname
# (aarch64). They agree only on x86_64, which is why getting this wrong is
# invisible until someone releases for ARM.
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) DEB_ARCH="amd64"; APPIMAGE_ARCH="amd64"; FEED_ARCH="x86_64" ;;
  aarch64) DEB_ARCH="arm64"; APPIMAGE_ARCH="aarch64"; FEED_ARCH="aarch64" ;;
  *) echo "❌ unsupported architecture $ARCH"; exit 1 ;;
esac
RPM_ARCH="$ARCH"

echo "🔨 Building nurb desktop v$VERSION for linux-$FEED_ARCH..."
make_artifacts_dir

# The config's bundle targets include the macOS app and dmg; name the Linux
# pair explicitly so the bundler never trips over targets this host cannot build.
npm run tauri build -- --bundles deb,rpm,appimage

# Unlike macOS, Linux has no updater tarball. Both packages are self-contained
# updater artifacts, so the bundler signs each one where it sits and the feed
# points at the package itself.
BUNDLE="src-tauri/target/release/bundle"
DEB="$BUNDLE/deb/nurb_${VERSION}_${DEB_ARCH}.deb"
# The trailing 1 is the RPM release number, which nothing here sets, so the
# bundler's default stands.
RPM="$BUNDLE/rpm/nurb-${VERSION}-1.${RPM_ARCH}.rpm"
APPIMAGE="$BUNDLE/appimage/nurb_${VERSION}_${APPIMAGE_ARCH}.AppImage"

for file in "$DEB" "$DEB.sig" "$RPM" "$APPIMAGE" "$APPIMAGE.sig"; do
  if [ ! -f "$file" ]; then
    echo "❌ the build did not produce $file"
    exit 1
  fi
done

# The bundler signs the .deb and the AppImage on its way past, but it does not
# count an .rpm as an updater artifact, so it leaves that one unsigned and an
# rpm-installed copy would have nothing to verify. Sign it here instead. The
# key may be the key itself or a path to it: the bundler takes either, while
# `signer sign` reads a path only through --private-key-path.
if [ ! -f "$RPM.sig" ]; then
  echo "🔏 Signing the .rpm, which the bundler leaves unsigned..."
  export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}"
  if [ -f "$TAURI_SIGNING_PRIVATE_KEY" ]; then
    npm run --silent tauri -- signer sign -f "$TAURI_SIGNING_PRIVATE_KEY" "$RPM"
  else
    npm run --silent tauri -- signer sign "$RPM"
  fi
  if [ ! -f "$RPM.sig" ]; then
    echo "❌ signing produced no $RPM.sig"
    exit 1
  fi
fi

# The published names carry the architecture, because a GitHub release redirect
# cannot pick an asset from the caller's machine.
DEB_NAME="nurb_${FEED_ARCH}.deb"
RPM_NAME="nurb_${FEED_ARCH}.rpm"
APPIMAGE_NAME="nurb-${FEED_ARCH}.AppImage"
cp "$DEB" "$ARTIFACTS/$DEB_NAME"
cp "$DEB.sig" "$ARTIFACTS/$DEB_NAME.sig"
cp "$RPM" "$ARTIFACTS/$RPM_NAME"
cp "$RPM.sig" "$ARTIFACTS/$RPM_NAME.sig"
cp "$APPIMAGE" "$ARTIFACTS/$APPIMAGE_NAME"
cp "$APPIMAGE.sig" "$ARTIFACTS/$APPIMAGE_NAME.sig"

echo "🔎 Checking the packages declare their dependencies..."
dpkg-deb --field "$ARTIFACTS/$DEB_NAME" Depends
# Only where rpm is installed, which a Debian build host will not have. The
# .rpm names bubblewrap, curl and xz itself and the bundler adds the shared
# libraries by soname, so this reads the whole set rather than the declared half.
if command -v rpm >/dev/null 2>&1; then
  rpm -qpR "$ARTIFACTS/$RPM_NAME"
else
  echo "   (rpm is not installed here, so the .rpm's requires go unchecked)"
fi

wait_for_tag

echo "🚀 Uploading missing linux-$FEED_ARCH artifacts to the $TAG release..."
upload_release_asset_set "$TAG" "linux-$FEED_ARCH" \
  "linux-$FEED_ARCH,linux-$FEED_ARCH-deb,linux-$FEED_ARCH-rpm" \
  "$ARTIFACTS/$DEB_NAME" "$ARTIFACTS/$DEB_NAME.sig" \
  "$ARTIFACTS/$RPM_NAME" "$ARTIFACTS/$RPM_NAME.sig" \
  "$ARTIFACTS/$APPIMAGE_NAME" "$ARTIFACTS/$APPIMAGE_NAME.sig"

# One entry per format, because the updater asks for its own package format
# first. A copy installed from the .deb looks for linux-<arch>-deb, and an
# rpm-installed one for linux-<arch>-rpm; either would otherwise fall through to
# the AppImage entry, download something its package manager cannot install, and
# never update again.
DOWNLOAD="https://github.com/$REPO/releases/download/$TAG"
publish_feed \
  --platform "linux-$FEED_ARCH=$DOWNLOAD/$APPIMAGE_NAME=$ARTIFACTS/$APPIMAGE_NAME.sig" \
  --platform "linux-$FEED_ARCH-deb=$DOWNLOAD/$DEB_NAME=$ARTIFACTS/$DEB_NAME.sig" \
  --platform "linux-$FEED_ARCH-rpm=$DOWNLOAD/$RPM_NAME=$ARTIFACTS/$RPM_NAME.sig"

echo "✅ Done! Release: https://github.com/$REPO/releases/tag/$TAG"
echo "   Debian/Ubuntu: https://github.com/$REPO/releases/latest/download/$DEB_NAME"
echo "   Fedora/RHEL: https://github.com/$REPO/releases/latest/download/$RPM_NAME"
echo "   AppImage: https://github.com/$REPO/releases/latest/download/$APPIMAGE_NAME"
echo "   If the Mac half has not run yet, latest.json carries Linux only until it does."
