#pragma once
// MSVC <intrin.h> for GCC: the x86 intrinsics where they exist, and _ReturnAddress
#if defined(__x86_64__) || defined(__i386__)
#include <x86intrin.h>
#endif
#ifndef _ReturnAddress
#define _ReturnAddress() __builtin_return_address(0)
#endif
