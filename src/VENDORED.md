# Vendored code

## src/ms2000r-emu
- Upstream: https://github.com/Tuth/ms2000r-emu (GPL-3.0, LICENSE.md in that folder), commit b5a5e5ca95e0f42ec98f2cc9c1f5cd2d99fffd75 (v0.9.8).
- Left out: source/gui, source/plugin (desktop ImGui/JUCE front ends), `source/core/h8s2350_emulator.cpp old`.
- Includes upstream's own vendored dsp56300 (external/dsp56300, The Usual Suspects, GPL-3.0) with upstream's patch series.
- Changes for the MPC port:
  1. `external/dsp56300/source/dsp56kEmu/jittrampoline.cpp`: an arm64 `generateExecUntilCyclesFunc()` (upstream's PERF-DSP-2
     batched block loop existed for x64 only). Bit-exact with the x86 build on a 20 s render; ~4% faster on the Live III.
  2. `external/dsp56300/source/dsp56kEmu/jittrampoline.h`: the debug hexdump of the execUntilCycles trampoline is skipped when
     the trampoline was not generated (it read a null pointer on arm64).
- Not a change, but needed on Linux: src/compat/intrin.h stands in for MSVC's <intrin.h>.
