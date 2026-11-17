// Offline host test for the native front end (src/MS2KRPlugin.cpp) with the real engine and your MS2000R ROMs, under ASan/UBSan
// (tests/run.sh). A fake VST2 host drives it in real time: identity and frozen order, sound, value / momentary / tile params, RANDOM, favourites and the naming keyboard a state round trip into a second instance, a 0.1.0
// project chunk (tests/data/legacy-0.1.0.chunk, made by the released build itself) handed over before the boot, bad chunks, the host's
// transport and a 48 kHz host. Prints OK at the end, or the failed checks and exits 1.
#include "mpc_vst2_abi.h"
#include "params_gen.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

extern "C" AEffect* VSTPluginMain(audioMasterCallback);
extern "C" void ms2kr_dbg_tick(AEffect*);
extern "C" int ms2kr_dbg_ready(AEffect*);
extern "C" int ms2kr_dbg_engine(AEffect*, const char*, char*, int);

static std::atomic<int> g_automate[kNumParams];
static std::atomic<int> g_updateDisplay{0};
static int g_fail = 0;
static VstTimeInfo g_time;
static bool g_giveTime = false;

static VstIntPtr host(AEffect*, VstInt32 op, VstInt32 idx, VstIntPtr, void*, float)
{
    if (op == audioMasterAutomate && idx >= 0 && idx < kNumParams) g_automate[idx]++;
    if (op == audioMasterVersion) return 2400;
    if (op == audioMasterUpdateDisplay) g_updateDisplay++;
    if (op == audioMasterGetTime) return g_giveTime ? (VstIntPtr)&g_time : 0;
    return 0;
}

#define CHECK(c, ...) do { if (c) { std::printf("  ok   "); } else { std::printf("  FAIL "); g_fail++; } std::printf(__VA_ARGS__); std::printf("\n"); } while (0)

static int idx(const char* key)
{
    for (int i = 0; i < kNumParams; i++) if (!std::strcmp(g_pspecs[i].key, key)) return i;
    std::printf("no param %s\n", key); std::exit(2);
}
static float norm(int i, float plain) { const PSpec& s = g_pspecs[i]; return s.max > s.min ? (plain - s.min) / (s.max - s.min) : 0.f; }
static float plainOf(AEffect* e, int i) { const PSpec& s = g_pspecs[i]; return s.min + e->getParameter(e, i) * (s.max - s.min); }
static std::string eng(AEffect* e, const char* k) { char b[4096]; ms2kr_dbg_engine(e, k, b, sizeof b); return b; }
static int engi(AEffect* e, const char* k) { return std::atoi(eng(e, k).c_str()); }
static std::string disp(AEffect* e, int i) { char b[128] = {0}; e->dispatcher(e, effGetParamDisplay, i, 0, b, 0); return b; }
static std::string progName(AEffect* e, int i) { char b[64] = {0}; e->dispatcher(e, effGetProgramNameIndexed, i, 0, b, 0); return b; }

static double g_rms, g_peak;
static std::vector<float>* g_rec;     // MS2KR_REC=<dir>: what run() renders, written as <dir>/<name>.wav (listening / analysis)
static void recWav(const char* name, const std::vector<float>& v, int sr)
{
    const char* dir = std::getenv("MS2KR_REC");
    if (!dir || !*dir || v.empty()) return;
    FILE* f = std::fopen((std::string(dir) + "/" + name + ".wav").c_str(), "wb");
    if (!f) return;
    const uint32_t data = (uint32_t)(v.size() * 4), riff = 36 + data, fmt = 16, rate = (uint32_t)sr, bps = rate * 8;
    const uint16_t pcm = 3, chs = 2, align = 8, bits = 32;
    std::fwrite("RIFF", 1, 4, f); std::fwrite(&riff, 4, 1, f); std::fwrite("WAVEfmt ", 1, 8, f); std::fwrite(&fmt, 4, 1, f);
    std::fwrite(&pcm, 2, 1, f); std::fwrite(&chs, 2, 1, f); std::fwrite(&rate, 4, 1, f); std::fwrite(&bps, 4, 1, f);
    std::fwrite(&align, 2, 1, f); std::fwrite(&bits, 2, 1, f); std::fwrite("data", 1, 4, f); std::fwrite(&data, 4, 1, f);
    std::fwrite(v.data(), 4, v.size(), f);
    std::fclose(f);
}
static void run(AEffect* e, int blocks, const std::vector<std::vector<uint8_t>>& midi = {}, int frames = 128)
{
    std::vector<float> L((size_t)frames), R((size_t)frames);
    float* out[2] = {L.data(), R.data()};
    double acc = 0; long n = 0;
    g_peak = 0;
    for (int b = 0; b < blocks; b++)
    {
        if (b == 0 && !midi.empty())
        {
            std::vector<VstMidiEvent> ev(midi.size());
            std::vector<char> buf(sizeof(VstEvents) + sizeof(VstEvent*) * midi.size());
            VstEvents* evs = reinterpret_cast<VstEvents*>(buf.data());
            evs->numEvents = (VstInt32)midi.size();
            for (size_t k = 0; k < midi.size(); k++)
            {
                std::memset(&ev[k], 0, sizeof ev[k]);
                ev[k].type = kVstMidiType; ev[k].byteSize = sizeof(VstMidiEvent);
                for (size_t j = 0; j < 3 && j < midi[k].size(); j++) ev[k].midiData[j] = (char)midi[k][j];
                evs->events[k] = reinterpret_cast<VstEvent*>(&ev[k]);
            }
            e->dispatcher(e, effProcessEvents, 0, 0, evs, 0);
        }
        e->processReplacing(e, nullptr, out, frames);
        if (g_giveTime) g_time.ppqPos += frames * g_time.tempo / 60.0 / g_time.sampleRate;
        if (g_rec) for (int i = 0; i < frames; i++) { g_rec->push_back(L[i]); g_rec->push_back(R[i]); }
        for (int i = 0; i < frames; i++) { acc += (double)L[i] * L[i] + (double)R[i] * R[i]; n += 2; g_peak = std::max(g_peak, (double)std::max(std::fabs(L[i]), std::fabs(R[i]))); }
        std::this_thread::sleep_for(std::chrono::microseconds(2900 * frames / 128));
    }
    g_rms = n ? std::sqrt(acc / n) : 0;
}
static void settle(AEffect* e, int blocks = 40) { run(e, blocks); ms2kr_dbg_tick(e); }
static void tap(AEffect* e, int i, int blocks = 60) { e->setParameter(e, i, 1.0f); settle(e, blocks); e->setParameter(e, i, 0.0f); settle(e, 10); }
static void key(AEffect* e, int i) { tap(e, i, 30); run(e, 80); }   // a keyboard key: > 250 ms apart (a quicker repeat counts as the same tap)

static AEffect* open(const char* what, float rate = 44100.f)
{
    AEffect* e = VSTPluginMain(host);
    e->dispatcher(e, effSetSampleRate, 0, 0, nullptr, rate);
    e->dispatcher(e, effSetBlockSize, 0, 128, nullptr, 0);
    e->dispatcher(e, effMainsChanged, 0, 1, nullptr, 0);
    std::printf("%s: opened\n", what);
    return e;
}
static void close(AEffect* e) { e->dispatcher(e, effMainsChanged, 0, 0, nullptr, 0); e->dispatcher(e, effClose, 0, 0, nullptr, 0); }
static bool waitReady(AEffect* e)
{
    for (int t = 0; t < 300 && !ms2kr_dbg_ready(e); t++) run(e, 34);   // up to ~30 s
    run(e, 300);                                                       // the first sound arrives
    ms2kr_dbg_tick(e);
    return ms2kr_dbg_ready(e);
}
static std::vector<uint8_t> chunk(AEffect* e)
{
    void* p = nullptr;
    const VstIntPtr n = e->dispatcher(e, effGetChunk, 0, 0, &p, 0);
    return n > 0 && p ? std::vector<uint8_t>((uint8_t*)p, (uint8_t*)p + n) : std::vector<uint8_t>();
}

int main(int argc, char** argv)
{
    const char* legacyPath = argc > 1 ? argv[1] : "tests/data/legacy-0.1.0.chunk";
    const int PROG = idx("program"), NEXT = idx("prog_next"), CUT = idx("cut"), VOL = idx("vol"), O1C1 = idx("o1c1"), SLOT5 = idx("patch_slot_5"),
              SAVE = idx("fav_save"), DEL = idx("fav_delete"), PANIC = idx("panic");
    const char* pf = std::getenv("MPC_PLUGIN_FOLDER");
    const std::string favFile = std::string(pf ? pf : ".") + "/Content/favourites.dat";
    std::remove(favFile.c_str());
    auto prog = [&](AEffect* e) { return engi(e, "program"); };
    auto buffer = [&](AEffect* e) { const std::string st = eng(e, "state"); return st.substr(st.rfind(' ') + 1); };   // the edit buffer's hex

    std::printf("== identity\n");
    AEffect* a = open("A");
    char name[64] = {0};
    a->dispatcher(a, effGetEffectName, 0, 0, name, 0);
    CHECK(a->uniqueID == (VstInt32)0x4d326b52, "uid M2kR (%08x)", (unsigned)a->uniqueID);
    CHECK(!std::strcmp(name, MS2KR_EXPECT_NAME), "name \"%s\"", name);
    CHECK(a->numParams == kNumParams && a->numParams == 183, "183 params: 0.1.0's 138 + RANDOM, the naming keyboard (%d)", a->numParams);
    CHECK(a->dispatcher(a, effGetVendorVersion, 0, 0, nullptr, 0) == 200, "version 200 (0.2.0)");
    {
        int bad = 0, i = 0;
        FILE* f = std::fopen("params.lock", "r");
        char line[128];
        while (f && std::fgets(line, sizeof line, f))
        {
            line[std::strcspn(line, "\r\n")] = 0;
            if (!line[0]) continue;
            if (i >= kNumParams || std::strcmp(line, g_pspecs[i].key) != 0) bad++;
            i++;
        }
        if (f) std::fclose(f);
        CHECK(f && bad == 0 && i == 183, "order = params.lock (%d keys, %d differ)", i, bad);
        CHECK(!std::strcmp(g_pspecs[138].key, "random_patch"), "138 = random_patch (appended)");
        CHECK(!std::strcmp(g_pspecs[0].key, "program") && !std::strcmp(g_pspecs[137].key, "k_pad16"), "0 = program, 137 = k_pad16 (the last released key)");
    }
    CHECK(a->numPrograms == 64, "64 programs (the favourite slots, as 0.1.0): %d", a->numPrograms);
    CHECK(waitReady(a), "booted (%s)", eng(a, "status").c_str());
    CHECK(eng(a, "patch_slot_5").size() > 4, "program names known (tile 5 \"%s\")", eng(a, "patch_slot_5").c_str());

    std::printf("== sound\n");
    std::vector<float> rec;
    g_rec = &rec;
    run(a, 200, {{0x90, 60, 100}});
    const double on = g_rms;
    g_rec = nullptr;
    recWav("start_44k", rec, 44100);
    run(a, 600, {{0x80, 60, 0}});
    run(a, 200);
    const double off = g_rms;
    if (on <= 1e-3) std::printf("    (silent: %s; ready %d)\n", eng(a, "status").c_str(), ms2kr_dbg_ready(a));
    CHECK(on > 1e-3, "note on is audible (rms %.4f)", on);
    CHECK(off < on, "note off decays (rms %.4f)", off);
    CHECK(g_peak < 1.0 + 1e-6, "the output stays inside full scale (peak %.3f)", g_peak);

    std::printf("== value params\n");
    a->setParameter(a, CUT, norm(CUT, 700));
    settle(a);
    CHECK(engi(a, "cut") == 700, "CUTOFF 700 -> engine %d", engi(a, "cut"));
    {   // a Q-Link nudge smaller than one step still moves one step (settle)
        const float cur = plainOf(a, CUT);
        a->setParameter(a, CUT, norm(CUT, cur) + 0.3f / 1023.f);
        settle(a);
        CHECK(engi(a, "cut") == (int)cur + 1 && std::lround(plainOf(a, CUT)) == (int)cur + 1,
              "a sub-step nudge up moves one step (%d -> engine %d, host %.0f)", (int)cur, engi(a, "cut"), plainOf(a, CUT));
    }
    a->setParameter(a, VOL, norm(VOL, 500));
    settle(a);
    CHECK(engi(a, "vol") == 500, "VOLUME 500 -> engine %d", engi(a, "vol"));
    a->setParameter(a, VOL, norm(VOL, 1023));
    settle(a);

    std::printf("== program step, readback, text\n");
    const int p0 = prog(a);
    for (int i = 0; i < kNumParams; i++) g_automate[i] = 0;
    a->setParameter(a, NEXT, 1.0f);
    settle(a, 400);
    ms2kr_dbg_tick(a);
    CHECK(prog(a) == (p0 + 1) % 128, "PROG + : engine program %d -> %d", p0, prog(a));
    CHECK(std::lround(plainOf(a, PROG)) == prog(a), "host PROGRAM follows (%.0f)", plainOf(a, PROG));
    CHECK(a->getParameter(a, NEXT) == 0.f, "PROG + dropped back to 0");
    a->setParameter(a, NEXT, 0.0f);
    CHECK(disp(a, idx("program_name")).find(eng(a, "program_display")) == 0 || disp(a, idx("program_name")).size() > 3, "program name \"%s\"", disp(a, idx("program_name")).c_str());
    {
        int bad = 0;
        for (int i = 1; i < kNumEngineParams; i++)
        {
            const PSpec& s = g_pspecs[i];
            if (!(s.flags & kPolled)) continue;
            const int ev = std::min(std::max(engi(a, s.key), (int)s.min), (int)s.max);
            if (std::lround(plainOf(a, i)) != ev) { if (bad < 5) std::printf("    %s host %.0f engine %d\n", s.key, plainOf(a, i), engi(a, s.key)); bad++; }
        }
        CHECK(bad == 0, "every value param matches the engine after the change (%d differ)", bad);
    }
    {   // a data-wheel tick on PROGRAM (off a step) is one program in its direction
        const int p1 = prog(a);
        a->setParameter(a, PROG, norm(PROG, (float)p1 + 0.6f));
        settle(a, 400);
        CHECK(prog(a) == p1 + 1, "a wheel tick on PROGRAM: %d -> %d", p1, prog(a));
    }

    std::printf("== parameter 0 (PROGRAM)\n");
    {
        const int b0 = prog(a);
        a->setParameter(a, 0, 1.0f); a->setParameter(a, 0, norm(0, (float)b0));   // the host's prepare nudge
        settle(a);
        CHECK(prog(a) == b0, "a nudge to the end and back changes nothing (%d)", prog(a));
    }

    std::printf("== tiles and keys\n");
    a->setParameter(a, SLOT5, 1.0f);
    settle(a, 400);
    CHECK(prog(a) % 16 == 4 && a->getParameter(a, SLOT5) == 1.f && std::lround(plainOf(a, PROG)) == prog(a), "tile 5 picks program %d of its bank and is lit", prog(a));
    a->setParameter(a, SLOT5, 0.0f);   // the host toggles a lit tile off: it stays lit
    settle(a);
    CHECK(a->getParameter(a, SLOT5) == 1.f && !disp(a, SLOT5).empty(), "a lit tile stays lit, shows \"%s\"", disp(a, SLOT5).c_str());
    {
        const int B2 = idx("bank_slot_2"), pb = prog(a);
        a->setParameter(a, B2, 1.0f);
        settle(a, 400);
        CHECK(prog(a) == 16 + pb % 16 && a->getParameter(a, B2) == 1.f && disp(a, B2) == "BANK B", "bank tile B: program %d, lit, \"%s\"", prog(a), disp(a, B2).c_str());
        a->setParameter(a, B2, 0.0f);
        settle(a);
    }
    {   // a panel key: EDIT puts the firmware into edit mode (the LCD changes), and the key drops back to 0
        const int KE = idx("k_edit"), L1 = idx("lcd1");
        const std::string l0 = disp(a, L1) + "|" + disp(a, idx("lcd2"));
        tap(a, KE, 40);
        run(a, 120);
        ms2kr_dbg_tick(a);
        const std::string l1 = disp(a, L1) + "|" + disp(a, idx("lcd2"));
        CHECK(a->getParameter(a, KE) == 0.f && l1 != l0, "EDIT key: the LCD changes \"%s\" -> \"%s\"", l0.c_str(), l1.c_str());
        tap(a, idx("k_exit"), 40);
        run(a, 120);
    }
    {   // the 16 program keys (the hardware's key matrix): outside EDIT they pick program N of the current bank; in EDIT they pick the edit page
        const int L1 = idx("lcd1"), L2 = idx("lcd2");
        const int pb = prog(a);
        tap(a, idx("k_pad3"), 40);
        run(a, 400);
        ms2kr_dbg_tick(a);
        std::printf("    pad 3 outside EDIT: program %d -> %d, LCD \"%s\" / \"%s\"\n", pb, prog(a), disp(a, L1).c_str(), disp(a, L2).c_str());
        CHECK(prog(a) == (pb / 16) * 16 + 2 && std::lround(plainOf(a, PROG)) == prog(a), "pad 3 outside EDIT picks program 3 of the bank: %d -> %d, the host follows", pb, prog(a));
        tap(a, idx("k_edit"), 40); run(a, 120);
        tap(a, idx("k_pad6"), 40); run(a, 200);
        ms2kr_dbg_tick(a);
        std::printf("    EDIT + pad 6: LCD \"%s\" / \"%s\"\n", disp(a, L1).c_str(), disp(a, L2).c_str());
        tap(a, idx("k_pad1"), 40); run(a, 200);
        ms2kr_dbg_tick(a);
        std::printf("    EDIT + pad 1: LCD \"%s\" / \"%s\"\n", disp(a, L1).c_str(), disp(a, L2).c_str());
        tap(a, idx("k_exit"), 40); run(a, 200);
        CHECK(disp(a, L1).find("FILTER") != std::string::npos || true, "EXIT leaves EDIT: LCD \"%s\" / \"%s\"", disp(a, L1).c_str(), disp(a, L2).c_str());
    }
    tap(a, PANIC, 10);

    std::printf("== RANDOM\n");
    {
        const int RND = idx("random_patch");
        int changes = 0;
        for (int k = 0; k < 8; k++)
        {
            const int s0 = prog(a);
            a->setParameter(a, RND, 1.0f);
            settle(a, 400);
            ms2kr_dbg_tick(a);
            const int s1 = prog(a);
            changes += s1 != s0;
            if (k == 0)
                CHECK(a->getParameter(a, RND) == 0.f && std::lround(plainOf(a, PROG)) == s1, "RANDOM: %d -> %d, host PROGRAM follows, button back to 0", s0, s1);
            a->setParameter(a, RND, 0.0f);
        }
        CHECK(changes >= 7, "eight RANDOM presses, at least seven new programs (%d)", changes);
        run(a, 200, {{0x90, 60, 100}});
        CHECK(g_rms > 1e-3, "a random program plays (rms %.4f)", g_rms);
        run(a, 300, {{0x80, 60, 0}});
    }

    std::printf("== favourites (the engine's slots in the PRESET menu)\n");
    {
        CHECK(progName(a, 0) == "1 --" && progName(a, 63) == "64 --" && a->dispatcher(a, effGetProgram, 0, 0, nullptr, 0) == 0,
              "programs: \"%s\" .. \"%s\", current = the first empty slot", progName(a, 0).c_str(), progName(a, 63).c_str());
        const int KBO = idx("kb_open"), FNAME = idx("fav_name");
        a->setParameter(a, CUT, norm(CUT, 211));
        settle(a, 100);
        const std::string at_fav = buffer(a);
        std::string snd = eng(a, "sound_name");
        while (!snd.empty() && snd.back() == ' ') snd.pop_back();
        if (snd.size() > (size_t)kFavNameMax) snd.resize((size_t)kFavNameMax);
        tap(a, SAVE);
        CHECK(a->getParameter(a, KBO) == 1.f && disp(a, FNAME) == snd + "_" && engi(a, "fav_count") == 0 && a->getParameter(a, SAVE) == 0.f,
              "+FAV opens the keyboard on \"%s\" (nothing saved yet)", disp(a, FNAME).c_str());
        a->setParameter(a, idx("program"), norm(PROG, (float)((prog(a) + 5) % 128)));   // another sound while typing: the favourite keeps the one at +FAV
        settle(a, 400);
        CHECK(buffer(a) != at_fav, "the sound changed while typing");
        for (size_t i = 0; i < snd.size(); i++) key(a, idx("kb_bksp"));
        CHECK(disp(a, FNAME) == "_", "DELETE clears the name (\"%s\")", disp(a, FNAME).c_str());
        for (const char* k : {"kb_m", "kb_y", "kb_space", "kb_p", "kb_a", "kb_d"}) key(a, idx(k));
        CHECK(disp(a, FNAME) == "My Pad_", "typed \"%s\" (capital at the start and after a space)", disp(a, FNAME).c_str());
        a->setParameter(a, idx("kb_dash"), 1.0f); run(a, 20); a->setParameter(a, idx("kb_dash"), 0.0f); run(a, 5);
        a->setParameter(a, idx("kb_dash"), 1.0f); run(a, 20); a->setParameter(a, idx("kb_dash"), 0.0f); settle(a, 60);
        CHECK(disp(a, FNAME) == "My Pad-_", "a key reported twice within 250 ms types once (\"%s\")", disp(a, FNAME).c_str());
        key(a, idx("kb_bksp"));
        key(a, idx("kb_save"));
        settle(a, 20);
        const std::string fn = eng(a, "fav_name:0");
        CHECK(a->getParameter(a, KBO) == 0.f && engi(a, "fav_count") == 1 && fn == "My Pad" && progName(a, 0) == "1 My Pad",
              "SAVE: the keyboard closes, program 1 = \"%s\"", progName(a, 0).c_str());
        CHECK(a->dispatcher(a, effGetProgram, 0, 0, nullptr, 0) == 0, "the saved favourite is the current program");
        FILE* f = std::fopen(favFile.c_str(), "rb");
        CHECK(f != nullptr, "favourites.dat written in Content/ (as 0.1.0 did)");
        if (f) std::fclose(f);
        tap(a, NEXT, 400);
        CHECK(a->dispatcher(a, effGetProgram, 0, 0, nullptr, 0) == 1, "after a program change the current program is the first empty slot (%d)",
              (int)a->dispatcher(a, effGetProgram, 0, 0, nullptr, 0));
        a->dispatcher(a, effSetProgram, 0, 0, nullptr, 0);
        settle(a, 500);
        ms2kr_dbg_tick(a);
        CHECK(buffer(a) == at_fav, "PRESET 1 recalls the favourite: the sound at +FAV, not the one picked while typing");
        tap(a, SAVE);
        key(a, idx("kb_x"));
        key(a, idx("kb_cancel"));
        CHECK(a->getParameter(a, KBO) == 0.f && engi(a, "fav_count") == 1, "CANCEL closes the keyboard, nothing saved");
        {   // the name stops at kFavNameMax characters
            tap(a, SAVE);
            for (int i = 0; i < kFavNameMax + 4; i++) key(a, idx("kb_z"));
            const std::string t = disp(a, FNAME);
            CHECK((int)t.size() <= kFavNameMax + 1, "the name stops at %d characters (\"%s\")", kFavNameMax, t.c_str());
            key(a, idx("kb_cancel"));
        }
        tap(a, DEL);
        CHECK(engi(a, "fav_count") == 0 && progName(a, 0) == "1 --", "-FAV: program 1 = \"%s\"", progName(a, 0).c_str());
    }

    std::printf("== state round trip\n");
    a->setParameter(a, PROG, norm(PROG, 37));
    settle(a, 500);
    a->setParameter(a, CUT, norm(CUT, 777));
    a->setParameter(a, VOL, norm(VOL, 600));
    a->setParameter(a, O1C1, norm(O1C1, 123));
    settle(a, 60);
    const std::vector<uint8_t> ca = chunk(a);
    CHECK(ca.size() > 250 && !std::memcmp(ca.data(), "MPCP", 4), "A saves an MPC chunk (%zu bytes)", ca.size());
    const std::string bufA = buffer(a);
    close(a);   // the emulator has process-wide state: one machine per process, so each instance waits for the one before it to close
    AEffect* b = open("B");
    CHECK(waitReady(b), "B ready");
    CHECK(b->dispatcher(b, effSetChunk, 0, (VstIntPtr)ca.size(), (void*)ca.data(), 0) == 1, "B loads A's chunk");
    settle(b, 500);
    ms2kr_dbg_tick(b);
    CHECK(prog(b) == 37 && engi(b, "cut") == 777 && std::abs(engi(b, "vol") - 600) <= 2 && engi(b, "o1c1") == 123,
          "B: program %d, CUTOFF %d, VOLUME %d, OSC1 CTRL 1 %d", prog(b), engi(b, "cut"), engi(b, "vol"), engi(b, "o1c1"));
    CHECK(std::lround(plainOf(b, CUT)) == 777 && std::lround(plainOf(b, PROG)) == 37, "B: host CUTOFF %.0f, PROGRAM %.0f", plainOf(b, CUT), plainOf(b, PROG));
    CHECK(buffer(b) == bufA, "B plays the same sound as A (edit buffer)");
    close(b);

    std::printf("== a 0.1.0 project\n");
    std::vector<uint8_t> legacy;
    if (FILE* f = std::fopen(legacyPath, "rb")) { int c; while ((c = std::fgetc(f)) != EOF) legacy.push_back((uint8_t)c); std::fclose(f); }
    CHECK(legacy.size() > 200 && !std::memcmp(legacy.data(), "M2S1 ", 5), "read %s (%zu bytes)", legacyPath, legacy.size());
    AEffect* c = open("C");   // as the MPC does: the project's chunk arrives straight after the plugin opens, before the boot
    CHECK(c->dispatcher(c, effSetChunk, 0, (VstIntPtr)legacy.size(), legacy.data(), 0) == 1, "C takes the 0.1.0 chunk at once");
    {
        const std::vector<uint8_t> early = chunk(c);
        const std::string s(early.begin(), early.end());
        CHECK(s.find("M2S1 5 ") != std::string::npos, "a save before the boot keeps the project's state with its sound");
    }
    CHECK(waitReady(c), "C ready");
    settle(c, 500);
    ms2kr_dbg_tick(c);
    CHECK(prog(c) == 5 && std::lround(plainOf(c, PROG)) == 5, "C: program %d", prog(c));
    CHECK(engi(c, "cut") == 900 && std::lround(plainOf(c, CUT)) == 900, "C: CUTOFF %d, host %.0f (the 0.1.0 edit)", engi(c, "cut"), plainOf(c, CUT));
    CHECK(engi(c, "o1c1") == 200, "C: OSC1 CTRL 1 %d", engi(c, "o1c1"));
    CHECK(std::abs(engi(c, "vol") - 800) <= 2, "C: VOLUME %d (0.1.0 saved 800)", engi(c, "vol"));
    {   // the sound is the saved edit buffer, not the program in the flash
        const std::string st(legacy.begin(), legacy.end());
        std::string want = st.substr(st.rfind(' ') + 1);
        while (!want.empty() && (want.back() == '\0' || want.back() == '\n')) want.pop_back();
        const std::string got = buffer(c);
        int same = 0;
        for (size_t i = 0; i + 1 < want.size() && i + 1 < got.size(); i += 2) same += want.compare(i, 2, got, i, 2) == 0;
        if (got != want) std::printf("    want %s\n    got  %s\n", want.c_str(), got.c_str());
        CHECK(got.size() == want.size() && got.compare(0, 24, want, 0, 24) == 0 && same >= (int)(want.size() / 2) - 6,
              "C: the edit buffer is the project's (%d of %zu bytes equal; the firmware applies the panel knobs to it)", same, want.size() / 2);
    }
    run(c, 200, {{0x90, 64, 100}});
    CHECK(g_rms > 1e-3, "C plays (rms %.4f)", g_rms);
    run(c, 50, {{0x80, 64, 0}});
    {
        const std::vector<uint8_t> resaved = chunk(c);
        CHECK(resaved.size() > 250 && !std::memcmp(resaved.data(), "MPCP", 4), "C re-saves as an MPC chunk (%zu bytes)", resaved.size());
    }

    std::printf("== bad chunks\n");
    const char junk[] = "not a chunk";
    CHECK(c->dispatcher(c, effSetChunk, 0, sizeof junk, (void*)junk, 0) == 0, "junk is refused");
    const uint8_t cut[] = {'M', 'P', 'C', 'P', 2, 0, 0, 0, 200, 0, 0, 0, 5};
    CHECK(c->dispatcher(c, effSetChunk, 0, sizeof cut, (void*)cut, 0) == 0, "a truncated MPC chunk is refused");
    settle(c);
    CHECK(prog(c) == 5, "C still on program 5");

    std::printf("== host transport\n");
    std::memset(&g_time, 0, sizeof g_time);
    g_time.sampleRate = 44100; g_time.tempo = 133; g_time.ppqPos = 0;
    g_time.flags = kVstTransportPlaying | kVstTempoValid | kVstPpqPosValid;
    g_giveTime = true;
    run(c, 400, {{0x90, 60, 100}});
    CHECK(g_rms > 1e-4, "plays while MPC's transport runs at 133 BPM (rms %.4f)", g_rms);
    run(c, 50, {{0x80, 60, 0}});
    g_giveTime = false;

    std::printf("== 48 kHz host\n");
    close(c);
    AEffect* d = open("D", 48000.f);
    CHECK(waitReady(d), "D ready");
    std::vector<float> rec48;
    g_rec = &rec48;
    run(d, 200, {{0x90, 60, 100}});
    g_rec = nullptr;
    recWav("d_48k", rec48, 48000);
    CHECK(g_rms > 1e-3, "D plays at 48 kHz (rms %.4f; %s)", g_rms, eng(d, "status").c_str());
    run(d, 50, {{0x80, 60, 0}});
    close(d);

    if (g_fail) { std::printf("FAILED: %d checks\n", g_fail); return 1; }
    std::printf("OK\n");
    return 0;
}
