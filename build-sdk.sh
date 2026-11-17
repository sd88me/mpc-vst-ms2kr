#!/usr/bin/env bash
# Build MS2KR 0.2 (the native front end src/MS2KRPlugin.cpp around the engine) into build/sdk/"sd88me - VST - MS2KR"/ (arm64 only, Gen2: the DSP
# emulator's JIT has no 32-bit ARM backend). The engine archive comes from ./build.sh engine aarch64 (Docker, gcc); the front end is compiled in
# the same image against the plugin framework headers. The 1.x wrapper build is still ./build.sh.
#   ./build-sdk.sh            gen params, engine archive, plugin .so, folder (plugin.json, version.xml, Plugin Skins, Content/roms)
#   ./build-sdk.sh test       tests/run.sh (ASan/UBSan, your ROMs) + the builder's host_sim on a native build
#   ./build-sdk.sh beta       the same as "MS2KR 2 Beta" (uid M2kB): installs next to the release; carries your ROMs inside its folder
# MPC_SDK: the plugin builder checkout. MPC_VST: mpc-vst-plugins (wrapper/engine.h). MS2K_ROMS: your ROM folder (flash.bin, boot-362(.ms2000).bin;
# default ~/roms/MS2000_Full_Firmware). ALSA_ROOT_A64 / ALSA_ROOT_X86: unpacked libasound2-dev packages (see build.sh).
set -euo pipefail
cd "$(dirname "$0")"
SDK="${MPC_SDK:-$HOME/mpc-plugin-builder-sdk}"
MV="${MPC_VST:-$HOME/mpc-vst-plugins}"
SRCROM="${MS2K_ROMS:-$HOME/roms/MS2000_Full_Firmware}"
[ -f "$SDK/framework/mpc_plugin.h" ] || { echo "need the plugin builder (MPC_SDK, now $SDK)" >&2; exit 1; }
[ -f "$MV/wrapper/engine.h" ] || { echo "need mpc-vst-plugins (MPC_VST, now $MV)" >&2; exit 1; }
IMAGE=osirus-a64-builder          # the 1.x build's image (scripts/Dockerfile): Debian bookworm, glibc 2.36
NAME="MS2KR"; UID_="'M','2','k','R'"; UIDS=M2kR; SLUG=ms2kr
if [ "${1:-}" = beta ]; then NAME="MS2KR 2 Beta"; UID_="'M','2','k','B'"; UIDS=M2kB; SLUG=ms2kr2beta; fi
FOLDER="build/sdk/sd88me - VST - $NAME"
python3 tools/gen_sdk_params.py

if [ "${1:-}" = test ]; then
  MS2KR_NAME="MS2KR" tests/run.sh
  # host_sim (needs glibc >= 2.38): a plain native build, a scratch plugin folder with your ROMs
  mkdir -p build/sdk-native
  libs=""; for l in libms2k_dsp.a emu/libms2000.a emu/dsp56300/source/dsp56kEmu/libdsp56kEmu.a emu/dsp56300/source/dsp56kBase/libdsp56kBase.a \
      emu/dsp56300/source/asmjit/libasmjit.a emu/dsp56300/source/vtuneSdk/libvtuneSdk.a; do libs="$libs build/x86/$l"; done
  ALSA="-lasound"; [ -n "${ALSA_ROOT_X86:-}" ] && ALSA="$ALSA_ROOT_X86/usr/lib/x86_64-linux-gnu/libasound.so"
  g++ -std=c++17 -O2 -g -fPIC -shared -fvisibility=hidden -I"$SDK/framework" -I"$MV/wrapper" -Isrc -o build/sdk-native/ms2kr.so src/MS2KRPlugin.cpp \
    -Wl,--start-group $libs -Wl,--end-group $ALSA -lpthread -ldl -lm
  scratch="$(mktemp -d)"; trap 'rm -rf "$scratch"' EXIT
  mkdir -p "$scratch/Content/roms"; cp "$SRCROM/flash.bin" "$scratch/Content/roms/"; cp plugin.json "$scratch/"
  for b in "$SRCROM/boot-362.ms2000.bin" "$SRCROM/full FW/boot-362.ms2000.bin" "$SRCROM/boot-362.bin"; do [ -f "$b" ] && { cp "$b" "$scratch/Content/roms/"; break; }; done
  HS="$SDK/.sdk-tools/host_sim"
  if [ ! -x "$HS" ]; then   # built on first use, as the SDK's build.py does
    mkdir -p "$SDK/.sdk-tools"
    g++ -std=c++17 -O2 -I"$SDK/framework" -I"$SDK/tools/host-sim" -o "$HS" "$SDK/tools/host-sim/host_sim.cpp" -ldl -lpthread -lm
  fi
  [ -n "${ALSA_ROOT_X86:-}" ] && export LD_LIBRARY_PATH="$ALSA_ROOT_X86/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  # dump: the JSON only (the emulator logs to stdout as it boots)
  MPC_PLUGIN_FOLDER="$scratch" "$HS" build/sdk-native/ms2kr.so dump 2>/dev/null | python3 -c '
import json, sys
t = sys.stdin.read(); d = json.JSONDecoder()
for i, c in enumerate(t):
    if c in "{[":
        try: obj, _ = d.raw_decode(t[i:]); break
        except ValueError: pass
else: sys.exit("host_sim dump: no JSON in its output")
json.dump(obj, sys.stdout, indent=1)' > build/sdk-native/params.json
  MPC_PLUGIN_FOLDER="$scratch" "$HS" build/sdk-native/ms2kr.so test --notes 60,64,67 --wav build/sdk-native/test.wav 2>&1 \
    | grep -v -E 'MIPS:|^ |Recv:|_log@|operator\(\)|Latency|Resampler|thread priority|Boot using|^\[|^=|^✅|^⚠'
  exit "${PIPESTATUS[0]}"
fi

: "${ALSA_ROOT_A64:=$HOME/alsa-a64/root}"; export ALSA_ROOT_A64
./build.sh engine aarch64      # vst/build/engine/libms2kr_all.a, from build/a64
rm -rf "$FOLDER"; mkdir -p "$FOLDER/VST" "$FOLDER/Plugin Skins" "$FOLDER/Content/roms"
docker image inspect $IMAGE >/dev/null 2>&1 || docker build -q -t $IMAGE -f scripts/Dockerfile scripts
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/b -v "$SDK":/sdk:ro -v "$MV":/mv:ro -w /b $IMAGE aarch64-linux-gnu-g++ \
  -std=c++17 -O2 -fPIC -shared -fvisibility=hidden -fvisibility-inlines-hidden -fno-gnu-unique -ffunction-sections -fdata-sections \
  -Wall -Wextra -Wno-format-truncation -mcpu=cortex-a55 -I/sdk/framework -I/mv/wrapper -Isrc \
  -DMS2KR_NAME="\"$NAME\"" -DMS2KR_UID="$UID_" \
  -o "$FOLDER/VST/$SLUG-arm64.so" src/MS2KRPlugin.cpp vst/build/engine/libms2kr_all.a \
  -Wl,--gc-sections -Wl,--version-script=/sdk/tools/exports.map -Wl,--exclude-libs,ALL -static-libstdc++ -static-libgcc vst/build/alsa/libasound.so -ldl -lpthread -lm
# the Live III has glibc 2.39; the image's is 2.36: check the newest symbol the .so needs, and that it exports only the entry point
newest=$(readelf -V "$FOLDER/VST/$SLUG-arm64.so" | grep -o 'GLIBC_[0-9.]*' | sort -V | tail -1)
echo "newest glibc symbol: $newest"
exports=$(readelf --dyn-syms -W "$FOLDER/VST/$SLUG-arm64.so" | awk '$5=="GLOBAL" && $7!="UND" {print $8}' | sort | tr '\n' ' ')
echo "exports: $exports"
python3 - "$NAME" "$SLUG" "$UIDS" "$FOLDER" <<'PY'
import json, sys
name, slug, uid, folder = sys.argv[1:]
m = json.load(open("plugin.json"))
m.update(name=name, uid=uid, file64="VST/%s-arm64.so" % slug)
json.dump(m, open(folder + "/plugin.json", "w"), indent=2)
open(folder + "/version.xml", "w").write('<?xml version="1.0" encoding="utf-8"?>\n<plugincontent version="1.0">\n    <version>%s.0</version>\n    <uiversion>0.1.0.0</uiversion>\n</plugincontent>\n' % m["version"])
PY
cp release/Content/roms/PUT_ROMS_HERE.txt "$FOLDER/Content/roms/"; cp LICENSE CREDITS.md "$FOLDER/"
# a beta for the device gets your ROMs inside its folder (mpc_remote.py update replaces the whole folder); never a release
if [ "${1:-}" = beta ]; then
  cp "$SRCROM/flash.bin" "$FOLDER/Content/roms/"
  for b in "$SRCROM/boot-362.ms2000.bin" "$SRCROM/full FW/boot-362.ms2000.bin" "$SRCROM/boot-362.bin"; do [ -f "$b" ] && { cp "$b" "$FOLDER/Content/roms/"; break; }; done
fi
# the native skin from tools/make_tui.py (skins/). Until it exists: the released 0.1.0 skin from the 1.x build (vst/build/skin), which binds the
# same parameter indices (it has no naming keyboard or RANDOM yet).
if [ -f tools/make_tui.py ]; then python3 tools/make_tui.py; fi
if [ -d skins ]; then cp -r skins/. "$FOLDER/Plugin Skins/"
elif [ -d "vst/build/skin/sd88me - VST - MS2KR/Plugin Skins" ]; then
  echo "note: no skins/ yet, using the 1.x skin"; cp -r "vst/build/skin/sd88me - VST - MS2KR/Plugin Skins/." "$FOLDER/Plugin Skins/"
else echo "no skin: run tools/make_tui.py or ./build.sh once" >&2; exit 1
fi
python3 "$SDK/tools/validate.py" "$FOLDER" || true
echo "built: $FOLDER"
