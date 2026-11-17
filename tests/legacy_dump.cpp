// tests/make_legacy_chunk.sh: drive the released 0.1.0 build (1.x wrapper + engine, x86) like a host and save its effGetChunk.
// Program 6 (G01 region, index 5), CUTOFF 900, OSC1 CTRL 1 200, VOLUME 800: edits that must come back.
//   legacy_dump <ms2kr.so> <out> <program idx> <cut idx> <o1c1 idx> <vol idx> <status idx>
#include <dlfcn.h>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

struct AEffect;
typedef intptr_t (*cb)(AEffect*, int32_t, int32_t, intptr_t, void*, float);
struct AEffect {
    int32_t magic;
    intptr_t (*d)(AEffect*, int32_t, int32_t, intptr_t, void*, float);
    void* proc;
    void (*setP)(AEffect*, int32_t, float);
    float (*getP)(AEffect*, int32_t);
    int32_t np, npar, ni, no, flags;
    intptr_t r1, r2;
    int32_t a, b, c;
    float io;
    void *obj, *user;
    int32_t uid, ver;
    void (*pr)(AEffect*, float**, float**, int32_t);
};
static intptr_t host(AEffect*, int32_t op, int32_t, intptr_t, void*, float) { return op == 1 ? 2400 : 0; }

static void run(AEffect* e, int blocks)
{
    float L[128], R[128], *out[2] = {L, R};
    for (int i = 0; i < blocks; i++) { e->pr(e, nullptr, out, 128); std::this_thread::sleep_for(std::chrono::microseconds(2900)); }
}

int main(int argc, char** argv)
{
    if (argc < 8) return 2;
    const int PROG = std::atoi(argv[3]), CUT = std::atoi(argv[4]), O1C1 = std::atoi(argv[5]), VOL = std::atoi(argv[6]), ST = std::atoi(argv[7]);
    void* h = dlopen(argv[1], RTLD_NOW);
    if (!h) { std::fprintf(stderr, "%s\n", dlerror()); return 1; }
    auto main_ = (AEffect* (*)(cb))dlsym(h, "VSTPluginMain");
    AEffect* e = main_(host);
    std::printf("0.1.0: uid=%x params=%d\n", e->uid, e->npar);
    if (e->npar != 138) { std::fprintf(stderr, "expected 138 params\n"); return 1; }
    e->d(e, 10, 0, 0, nullptr, 44100.f);
    e->d(e, 11, 0, 128, nullptr, 0);
    e->d(e, 12, 0, 1, nullptr, 0);
    char disp[128] = {0};
    for (int t = 0; t < 300; t++)   // up to ~30 s for the boot
    {
        run(e, 34);
        e->d(e, 7, ST, 0, disp, 0);
        if (!std::strncmp(disp, "ready", 5)) break;
    }
    std::printf("status: %s\n", disp);
    if (std::strncmp(disp, "ready", 5)) return 1;
    e->setP(e, PROG, 5.0f / 127.0f);
    run(e, 1500);
    e->setP(e, CUT, 900.0f / 1023.0f);
    e->setP(e, O1C1, 200.0f / 1023.0f);
    e->setP(e, VOL, 800.0f / 1023.0f);
    run(e, 600);
    void* chunk = nullptr;
    const intptr_t n = e->d(e, 23, 0, 0, &chunk, 0);
    if (n <= 0 || !chunk) { std::fprintf(stderr, "no chunk\n"); return 1; }
    if (std::strncmp((const char*)chunk, "M2S1", 4)) { std::fprintf(stderr, "not an M2S1 chunk: %.60s\n", (const char*)chunk); return 1; }
    FILE* f = std::fopen(argv[2], "wb");
    std::fwrite(chunk, 1, (size_t)n, f);
    std::fclose(f);
    std::printf("wrote %s (%ld bytes): %.100s...\n", argv[2], (long)n, (const char*)chunk);
    e->d(e, 12, 0, 0, nullptr, 0);
    e->d(e, 1, 0, 0, nullptr, 0);
    return 0;
}
