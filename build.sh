#!/usr/bin/env bash
# Build MS2KR. The engine (ms2000r-emu's core + src/dsp) is built with CMake into one static archive,
# vst/build/engine/libms2kr_all.a, which vst/vst.json links into the plugin through mpc-vst-plugins' tools/build_port.sh.
#   ./build.sh engine [x86|aarch64]   just the archive (default aarch64, cross-compiled in Docker)
#   ./build.sh test                   x86 engine test (needs ROMs: MS2K_TEST_DIR=<dir with roms/>)
#   ./build.sh [all]                  aarch64 engine + ms2kr.so in vst/build/aarch64/ (Gen2)
# MPC_VST: checkout of mpc-vst-plugins (default ~/mpc-vst-plugins). ALSA_ROOT_A64 / ALSA_ROOT_X86: unpacked libasound2-dev.
set -euo pipefail
cd "$(dirname "$0")"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins}"
IMAGE=osirus-a64-builder   # Debian bookworm cross toolchain (scripts/Dockerfile)
LIBS="libms2k_dsp.a emu/libms2000.a emu/dsp56300/source/dsp56kEmu/libdsp56kEmu.a emu/dsp56300/source/dsp56kBase/libdsp56kBase.a emu/dsp56300/source/asmjit/libasmjit.a emu/dsp56300/source/vtuneSdk/libvtuneSdk.a"

merge() {   # merge <ar> <build dir>
  local AR="$1" B="$2" out="vst/build/engine/libms2kr_all.a"
  mkdir -p vst/build/engine; rm -f "$out"
  { echo "CREATE $out"; for l in $LIBS; do [ -f "$B/$l" ] || { echo "missing $B/$l" >&2; exit 1; }; echo "ADDLIB $B/$l"; done
    echo "SAVE"; echo "END"; } | $AR -M
  echo "engine archive: $out ($(du -h $out | cut -f1))"
}

a64() {   # a64 <cxxflags> <build dir> <targets...>: cross-build in Docker
  local FL="$1" B="$2"; shift 2
  docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/b -v "$MPC_VST":/mv:ro -v "$ALSA_ROOT_A64":/alsa:ro -w /b $IMAGE bash -euc "
    cmake -S . -B $B -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/aarch64-toolchain.cmake -DCMAKE_BUILD_TYPE=Release -DMPC_VST=/mv \\
      -DCMAKE_CXX_FLAGS='$FL' -DALSA_INCLUDE_DIR=/alsa/usr/include -DALSA_LIBRARY=/alsa/usr/lib/aarch64-linux-gnu/libasound.so >/dev/null
    cmake --build $B --target $* -j\$(nproc)"
}

# PGO training on the Live III: an instrumented engine test run there (DEVICE=root@<address>, ROMs in DEVICE_DIR/mod/roms)
pgo_train() {
  : "${DEVICE:?set DEVICE=root@<live3>}"; local D="${DEVICE_DIR:-/nvme/ms2k-bench}"
  a64 "-mcpu=cortex-a55 -fprofile-generate -fprofile-update=atomic -fprofile-dir=/tmp/ms2kpgo" build/a64gen ms2k_engine_test
  scp -q build/a64gen/ms2k_engine_test "$DEVICE:$D/ms2k_engine_test_gen"
  ssh "$DEVICE" "rm -rf /tmp/ms2kpgo; cd $D && ./ms2k_engine_test_gen $D/mod >/dev/null 2>&1; ls /tmp/ms2kpgo | wc -l"
  rm -rf build/pgo-a64; mkdir -p build/pgo-a64; scp -q -r "$DEVICE:/tmp/ms2kpgo/." build/pgo-a64/
  # the profiles name the object paths of build/a64gen: rename them for build/a64
  for f in build/pgo-a64/*.gcda; do mv "$f" "${f//a64gen/a64}"; done
  echo "profile: $(ls build/pgo-a64 | wc -l) files"
}

engine() {
  case "${1:-aarch64}" in
    x86)
      cmake -S . -B build/x86 -G Ninja -DCMAKE_BUILD_TYPE=Release -DMPC_VST="$MPC_VST" \
        ${ALSA_ROOT_X86:+-DALSA_INCLUDE_DIR=$ALSA_ROOT_X86/usr/include -DALSA_LIBRARY=$ALSA_ROOT_X86/usr/lib/x86_64-linux-gnu/libasound.so} >/dev/null
      cmake --build build/x86 --target ms2k_dsp ms2k_engine_test -j"$(nproc)"
      merge ar build/x86 ;;
    aarch64)
      : "${ALSA_ROOT_A64:?set ALSA_ROOT_A64 to an unpacked libasound2-dev:arm64}"
      docker image inspect $IMAGE >/dev/null 2>&1 || docker build -q -t $IMAGE -f scripts/Dockerfile scripts
      # PGO: build/pgo-a64/*.gcda from a training run on the device (./build.sh pgo-train); without it, a plain -O3 build
      local PGO=""; [ -n "$(ls build/pgo-a64/*.gcda 2>/dev/null)" ] && PGO="-fprofile-use -fprofile-dir=/b/build/pgo-a64 -fprofile-partial-training -Wno-missing-profile -Wno-coverage-mismatch"
      a64 "-mcpu=cortex-a55 $PGO" build/a64 ms2k_dsp
      mkdir -p vst/build/alsa; cp -L "$ALSA_ROOT_A64/usr/lib/aarch64-linux-gnu/libasound.so" vst/build/alsa/libasound.so   # linked by path (vst.json); the device has libasound.so.2
      merge "docker run --rm -i -u $(id -u):$(id -g) -v $PWD:/b -w /b $IMAGE aarch64-linux-gnu-ar" build/a64 ;;
    *) echo "unknown arch $1" >&2; exit 1 ;;
  esac
}

case "${1:-all}" in
  engine) engine "${2:-aarch64}" ;;
  pgo-train) pgo_train ;;
  test)   engine x86; build/x86/ms2k_engine_test "${MS2K_TEST_DIR:?set MS2K_TEST_DIR}" ;;
  all)    python3 tools/gen_params.py; engine aarch64; "$MPC_VST/tools/build_port.sh" vst/vst.json aarch64 ;;
  *) sed -n 2,7p "$0"; exit 1 ;;
esac
