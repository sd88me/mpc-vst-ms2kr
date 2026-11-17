#!/usr/bin/env bash
# Make tests/data/legacy-0.1.0.chunk: what a project saved with the released 0.1.0 build stores (effGetChunk), from that build's own code.
# Builds the release-day tree (engine at v0.1.0 + mpc-vst-plugins' wrapper of the day) for x86 as a shared library, loads it like a host
# with your ROMs, and saves the chunk. Not committed: it carries a ROM program's bytes (tests/data is ignored).
# MS2K_ROMS: a folder with flash.bin and boot-362(.ms2000).bin (default ~/roms/MS2000_Full_Firmware, boot from "full FW"). MPC_VST: mpc-vst-plugins.
set -euo pipefail
cd "$(dirname "$0")/.."
MV="${MPC_VST:-$HOME/mpc-vst-plugins}"
SRCROM="${MS2K_ROMS:-$HOME/roms/MS2000_Full_Firmware}"
W=build/legacy; rm -rf "$W"; mkdir -p "$W/src" "$W/mv" "$W/plug/Content/roms" tests/data
git archive v0.1.0 | tar -x -C "$W/src"
MVREV="$(git -C "$MV" rev-list -1 --before=2026-11-03T11:37+11:00 HEAD)"   # the wrapper of the released ms2kr.so (built 2026-11-03 11:37)
git -C "$MV" archive "$MVREV" wrapper tools | tar -x -C "$W/mv"
MV="$(pwd)/$W/mv"
cp "$SRCROM/flash.bin" "$W/plug/Content/roms/"
for b in "$SRCROM/boot-362.ms2000.bin" "$SRCROM/full FW/boot-362.ms2000.bin" "$SRCROM/boot-362.bin"; do [ -f "$b" ] && { cp "$b" "$W/plug/Content/roms/"; break; }; done
( cd "$W/src" && python3 "$MV/tools/gen_vst.py" vst/vst.json --params-h >/dev/null )
n=$(grep -c '^    {"' "$W/src/vst/build/params.h"); [ "$n" = 138 ] || { echo "the v0.1.0 table has $n params, not 138" >&2; exit 1; }
cmake -S "$W/src" -B "$W/eng" -G Ninja -DCMAKE_BUILD_TYPE=Release -DMPC_VST="$MV" ${ALSA_ROOT_X86:+-DALSA_INCLUDE_DIR=$ALSA_ROOT_X86/usr/include -DALSA_LIBRARY=$ALSA_ROOT_X86/usr/lib/x86_64-linux-gnu/libasound.so} >/dev/null
cmake --build "$W/eng" --target ms2k_dsp -j"$(nproc)" >/dev/null
B="$W/eng"; libs=""
for l in libms2k_dsp.a emu/libms2000.a emu/dsp56300/source/dsp56kEmu/libdsp56kEmu.a emu/dsp56300/source/dsp56kBase/libdsp56kBase.a \
         emu/dsp56300/source/asmjit/libasmjit.a emu/dsp56300/source/vtuneSdk/libvtuneSdk.a; do libs="$libs $B/$l"; done
gcc -O1 -g -fPIC -std=gnu11 -DMODULE_SUBDIR='"Content"' -DHAS_DISPLAY_REV=1 -DDISPLAY_REV_NO_UPDATE=1 -DPARAM_TEXT_MAX=64 \
    -I"$W/src/vst/build" -I"$MV/wrapper" -c "$MV/wrapper/vst2_wrap.c" -o "$W/vst2_wrap.o"
g++ -shared -o "$W/plug/ms2kr.so" "$W/vst2_wrap.o" -Wl,--start-group $libs -Wl,--end-group -lpthread -lm -ldl ${ALSA_ROOT_X86:+"$ALSA_ROOT_X86/usr/lib/x86_64-linux-gnu/libasound.so"}
g++ -O1 -g -std=c++17 -o "$W/dump" tests/legacy_dump.cpp -ldl -lpthread
at() { grep -n -x "$1" params.lock | cut -d: -f1 | awk '{print $1 - 1}'; }
"$W/dump" "$W/plug/ms2kr.so" tests/data/legacy-0.1.0.chunk "$(at program)" "$(at cut)" "$(at o1c1)" "$(at vol)" "$(at status)"
