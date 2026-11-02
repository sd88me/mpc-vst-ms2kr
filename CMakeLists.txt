cmake_minimum_required(VERSION 3.16)
project(ms2000r_mpc VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# As Osirus: everything hidden, no STB_GNU_UNIQUE symbols, so ms2000r.so exports only VSTPluginMain and can be unloaded.
# src/compat: <intrin.h> for GCC (the vendored dsp56300 includes the MSVC header).
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fvisibility=hidden -fvisibility-inlines-hidden -fno-gnu-unique -isystem ${CMAKE_CURRENT_SOURCE_DIR}/src/compat")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -fvisibility=hidden")

# the emulator (vendored, src/VENDORED.md): its CMake builds the "ms2000" core library (and the dsp56300 libraries)
set(EMU ${CMAKE_CURRENT_SOURCE_DIR}/src/ms2000r-emu)
add_subdirectory(${EMU} ${CMAKE_BINARY_DIR}/emu EXCLUDE_FROM_ALL)

if(NOT MPC_VST)
  set(MPC_VST $ENV{HOME}/mpc-vst-plugins)
endif()
add_library(ms2k_dsp STATIC src/dsp/ms2k_engine.cpp)
target_include_directories(ms2k_dsp PUBLIC ${EMU}/source ${EMU}/source/core ${EMU}/external/dsp56300/source ${MPC_VST}/wrapper)
target_link_libraries(ms2k_dsp PUBLIC ms2000)
# the emulator's headers expect its force-included platform shim (MSVC keywords for GCC)
target_compile_options(ms2k_dsp PRIVATE -include ${EMU}/source/core/platform_compat.h)

add_executable(ms2k_engine_test test/engine_test.cpp)
target_link_libraries(ms2k_engine_test PRIVATE ms2k_dsp)
