#!/usr/bin/env bash
# The release zips, from the release build (build/sdk/"sd88me - VST - MS2KR", made by ./build-sdk.sh):
#   dist/MS2KR-<ver>-mpc-aarch64.zip   install.sh / uninstall.sh (MPC.settings) for 64-bit MPCs, made by mpc-vst-plugins' tools/release.py;
#                                      it upgrades a 0.1.0 install in place
#   dist/MS2KR-<ver>-mpc-sdk.zip       the plugin folder for "VST2 Plugins" (tools/sdk_zip.py)
#   dist/MS2KR-<ver>-SHA256SUMS.txt
# As in 0.1.0 the .so is ms2kr.so at the folder root (plugin.json names it, so the plugin finds its folder and Content/ beside it).
# User data, kept on upgrade and uninstall: Content/roms (your ROMs), Content/memory (the machine's stored programs and GLOBAL settings),
# Content/favourites.dat (0.1.0's installer did not list this one). No ROM is ever packed.
# MPC_VST: mpc-vst-plugins with tools/release.py and tools/sdk_zip.py.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins-postlaunch}"
[ -f "$MPC_VST/tools/release.py" ] && [ -f "$MPC_VST/tools/sdk_zip.py" ] || { echo "need mpc-vst-plugins with tools/sdk_zip.py (MPC_VST)" >&2; exit 1; }
DIR="sd88me - VST - MS2KR"; SRC="$here/build/sdk/$DIR"
[ -f "$SRC/VST/ms2kr-arm64.so" ] || { echo "missing $SRC: run ./build-sdk.sh first" >&2; exit 1; }
VER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$SRC/plugin.json")
python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m["uid"]=="M2kR" and "Beta" not in m["name"] else "not the release identity")' "$SRC/plugin.json"
out="$here/dist"; mkdir -p "$out"
st="$here/build/catalog/aarch64"; rm -rf "$st"; mkdir -p "$st/$DIR" "$st/extra"
cp -r "$SRC/Plugin Skins" "$SRC/version.xml" "$st/$DIR/"
python3 - "$SRC/plugin.json" "$st/$DIR/plugin.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m.pop("file32", None)
m["file64"] = "ms2kr.so"
json.dump(m, open(sys.argv[2], "w"), indent=2)
PY
cp "$SRC/VST/ms2kr-arm64.so" "$st/ms2kr.so"
cp -r "$here/release/Content/." "$st/extra/"; cp "$here/LICENSE" "$here/CREDITS.md" "$st/extra/"
# nothing of the user's may ride along: only the placeholder
if find "$st" -type f | grep -v -E 'PUT_ROMS_HERE\.txt$' | grep -i -E '/(roms|memory)/|\.(bin|syx|mid|nvram)$|favourites'; then
  echo "refusing: user files in the package" >&2; exit 1
fi
printf '<PLUGIN name="MS2KR" descriptiveName="MS2KR" format="VST" category="Synth" manufacturer="sd88me" version="%s" file="ms2kr.so" uid="4d326b52" isInstrument="1" fileTime="0" infoUpdateTime="0" numInputs="0" numOutputs="2" isShell="0"/>\n' "$VER" > "$st/entry.xml"
python3 "$MPC_VST/tools/release.py" --so "$st/ms2kr.so" --skin "$st/$DIR" --entry "$st/entry.xml" --version "$VER" --extra "$st/extra:Content" \
  --user-data Content/roms --user-data Content/memory --user-data Content/favourites.dat \
  --repo sd88me/mpc-vst-ms2kr --license GPL-3.0-only --id ms2kr \
  --requires "64-bit MPC (Live III and others) and your own MS2000R firmware dump (flash.bin and boot-362.bin)" \
  --about "Korg MS2000R emulation: the synthesizer's own firmware on an emulated H8S and DSP56362, with a native MPC panel, RANDOM and named favourites." \
  -o "$st/dist"
z=$(ls "$st/dist"/*.zip); cp "$z" "$out/MS2KR-$VER-mpc-aarch64.zip"
python3 "$here/tools/scrub_zip.py" "$out/MS2KR-$VER-mpc-aarch64.zip"
python3 "$MPC_VST/tools/catalog_check.py" "$out/MS2KR-$VER-mpc-aarch64.zip" --catalog --require-portable --expect-id ms2kr --expect-repo sd88me/mpc-vst-ms2kr
python3 "$MPC_VST/tools/sdk_zip.py" "$out/MS2KR-$VER-mpc-sdk.zip" "$out/MS2KR-$VER-mpc-aarch64.zip"
for f in "$out/MS2KR-$VER-mpc-aarch64.zip" "$out/MS2KR-$VER-mpc-sdk.zip"; do   # last guard: no ROM-like file in either zip
  if python3 -I -m zipfile -l "$f" | grep -i -E '\.(bin|syx|rom|nvram)\b|\.mid\b|favourites' | grep -v PUT_; then echo "refusing: a user or ROM-like file in $f" >&2; exit 1; fi
done
(cd "$out" && sha256sum "MS2KR-$VER-mpc-aarch64.zip" "MS2KR-$VER-mpc-sdk.zip" > "MS2KR-$VER-SHA256SUMS.txt")
ls -la "$out"/MS2KR-"$VER"-*
