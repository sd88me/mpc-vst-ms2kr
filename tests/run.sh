#!/usr/bin/env bash
# Offline x86 test under ASan/UBSan (no device): the native front end + the real engine and your ROMs, driven by tests/host_test.cpp in
# real time. Must print OK. MS2K_ROMS: a folder with flash.bin and boot-362(.ms2000).bin (default ~/roms/MS2000_Full_Firmware, the boot
# ROM from its "full FW" folder). MS2KR_NAME: the build's name (beta tests). ALSA_ROOT_X86: an unpacked libasound2-dev (the emulator's audio
# output links libasound).
set -euo pipefail
cd "$(dirname "$0")/.."
SDK="${MPC_SDK:-$HOME/mpc-plugin-builder-sdk}"
MV="${MPC_VST:-$HOME/mpc-vst-plugins}"
SRCROM="${MS2K_ROMS:-$HOME/roms/MS2000_Full_Firmware}"
python3 tools/gen_sdk_params.py >/dev/null
# A project chunk saved by the released 0.1.0 build, made from that build's own code and your ROMs (not committed: it holds a ROM program).
[ -f tests/data/legacy-0.1.0.chunk ] || tests/make_legacy_chunk.sh >/dev/null 2>&1
# the engine (unsanitised, Release) for x86, in its own build dir: vst/build/engine/ holds the aarch64 archive
cmake -S . -B build/x86 -G Ninja -DCMAKE_BUILD_TYPE=Release -DMPC_VST="$MV" \
  ${ALSA_ROOT_X86:+-DALSA_INCLUDE_DIR=$ALSA_ROOT_X86/usr/include -DALSA_LIBRARY=$ALSA_ROOT_X86/usr/lib/x86_64-linux-gnu/libasound.so} >/dev/null
cmake --build build/x86 --target ms2k_dsp -j"$(nproc)" > build/engine-x86.log 2>&1 || { grep -E "error" build/engine-x86.log | head -20; exit 1; }
B=build/x86; libs=""
for l in libms2k_dsp.a emu/libms2000.a emu/dsp56300/source/dsp56kEmu/libdsp56kEmu.a emu/dsp56300/source/dsp56kBase/libdsp56kBase.a \
         emu/dsp56300/source/asmjit/libasmjit.a emu/dsp56300/source/vtuneSdk/libvtuneSdk.a; do libs="$libs $B/$l"; done
T=build/test; mkdir -p "$T"
S="-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -O1 -g -std=c++17 -pthread"
N="${MS2KR_NAME:-MS2KR}"
g++ $S -Wall -Wextra -DMS2KR_TEST -DMS2KR_NAME="\"$N\"" -I"$SDK/framework" -I"$MV/wrapper" -Isrc -c src/MS2KRPlugin.cpp -o "$T/plugin.o"
g++ $S -DMS2KR_EXPECT_NAME="\"$N\"" -I"$SDK/framework" -Isrc -c tests/host_test.cpp -o "$T/host_test.o"
ALSA=""; [ -n "${ALSA_ROOT_X86:-}" ] && ALSA="$ALSA_ROOT_X86/usr/lib/x86_64-linux-gnu/libasound.so" || ALSA="-lasound"
g++ $S -o "$T/ms2krtest" "$T/plugin.o" "$T/host_test.o" -Wl,--start-group $libs -Wl,--end-group $ALSA -ldl -lm
pf="$(mktemp -d)"; trap 'rm -rf "$pf"' EXIT
mkdir -p "$pf/Content/roms"; cp "$SRCROM/flash.bin" "$pf/Content/roms/"; cp plugin.json "$pf/"
for b in "$SRCROM/boot-362.ms2000.bin" "$SRCROM/full FW/boot-362.ms2000.bin" "$SRCROM/boot-362.bin"; do [ -f "$b" ] && { cp "$b" "$pf/Content/roms/"; break; }; done
set +e
export MS2KR_REC="${MS2KR_REC:-}" MPC_PLUGIN_FOLDER="$pf" ASAN_OPTIONS=detect_leaks=1
[ -n "${ALSA_ROOT_X86:-}" ] && export LD_LIBRARY_PATH="$ALSA_ROOT_X86/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$T/ms2krtest" tests/data/legacy-0.1.0.chunk > "$T/log.txt" 2>&1
st=$?
grep -E '^(== |  ok   |  FAIL |OK$|FAILED|[A-DUW]: opened|    \(|    [A-Za-z0-9_]+ host )|ERROR: |runtime error' "$T/log.txt" | tail -${TAIL:-120}
exit $st
