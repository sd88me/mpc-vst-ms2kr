#!/usr/bin/env bash
# Build the release zip (no ROMs in it) and check it against the plugin catalog's rules.
#   ./release.sh <version>            e.g. ./release.sh 0.2.3   -> dist/MS2KR-<version>-mpc-aarch64.zip
# Then publish it: gh release create v<version> dist/MS2KR-<version>-mpc-aarch64.zip --title "MS2KR <version>" --notes-file <notes>
# MPC_VST: checkout of mpc-vst-plugins (default ~/mpc-vst-plugins), on a branch with the skin tool's `vy=` (PR #550 or newer main).
set -euo pipefail
cd "$(dirname "$0")"
VER="${1:?usage: ./release.sh <version>}"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins}"
[ -n "${SKIP_BUILD:-}" ] || ./build.sh all
rm -rf "dist/MS2KR-$VER-mpc-aarch64.zip"
EXTRA="$(mktemp -d)"; trap 'rm -rf "$EXTRA"' EXIT
cp -r release/Content/. "$EXTRA/"; cp LICENSE CREDITS.md "$EXTRA/"        # the installed plugin folder carries its licence and credits
python3 "$MPC_VST/tools/release.py" --so vst/build/aarch64/ms2kr.so --skin "vst/build/skin/sd88me - VST - MS2KR" \
  --entry vst/build/pluginlist-entry.xml --version "$VER" --extra "$EXTRA:Content" \
  --repo sd88me/mpc-vst-ms2kr --license GPL-3.0-only --id ms2kr --user-data Content/roms --user-data Content/memory --requires "your own MS2000R firmware dump (flash.bin and boot-362.bin)" -o dist
python3 "$MPC_VST/tools/catalog_check.py" "dist/MS2KR-$VER-mpc-aarch64.zip" --catalog --expect-id ms2kr --expect-repo sd88me/mpc-vst-ms2kr
# the package must carry no ROM: refuse anything that looks like one
if python3 -I -m zipfile -l "dist/MS2KR-$VER-mpc-aarch64.zip" | grep -i -E '\.(bin|mid|syx|rom)\b' | grep -v "PUT_"; then
  echo "refusing: a ROM-like file is in the zip" >&2; exit 1
fi
echo "ok: dist/MS2KR-$VER-mpc-aarch64.zip"
