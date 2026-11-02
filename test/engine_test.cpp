// ms2k_engine_test <module dir with roms/> [out.wav]: drives the engine as vst2_wrap.c does (44.1 kHz, 128-frame blocks)
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>
extern "C" {
#include "engine.h"
}

static int fails = 0;
#define CHECK(c, ...) do { if (c) std::printf("  ok   " __VA_ARGS__); else { std::printf("  FAIL " __VA_ARGS__); ++fails; } std::printf("\n"); } while (0)

static std::string get(const mpc_engine_t* e, void* i, const char* k) { char b[8192] = {}; return e->get_param(i, k, b, sizeof b) > 0 ? b : "<none>"; }

int main(int argc, char** argv)
{
    if (argc < 2) { std::fprintf(stderr, "usage: %s <module dir> [out.wav]\n", argv[0]); return 2; }
    const mpc_engine_t* e = mpc_engine();
    void* in = e->create(argv[1]);
    std::vector<int16_t> blk(256), wav;
    double worst = 0, sum = 0; long nblk = 0; std::vector<double> times;
    auto next = std::chrono::steady_clock::now();
    auto block = [&](bool keep) {
        next += std::chrono::microseconds(2902);
        std::this_thread::sleep_until(next);
        const auto t0 = std::chrono::steady_clock::now();
        e->render(in, blk.data(), 128);
        const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        if (keep) { times.push_back(ms); sum += ms; worst = std::max(worst, ms); ++nblk; wav.insert(wav.end(), blk.begin(), blk.end()); }
    };
    auto play = [&](double s, bool keep = true) { for (long i = 0; i < long(s * 44100 / 128); ++i) block(keep); };

    std::printf("boot\n");
    for (int i = 0; i < 600 && get(e, in, "status").rfind("ready", 0) != 0; ++i) {
        if (get(e, in, "status").find("ROMs missing") != std::string::npos || get(e, in, "status").find("did not") != std::string::npos) break;
        block(false); std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    std::printf("  status: %s\n", get(e, in, "status").c_str());
    CHECK(get(e, in, "status").rfind("ready", 0) == 0, "machine ready");
    next = std::chrono::steady_clock::now();   // pace from here (the boot wait above is not real-time playing)
    if (fails) return 1;
    play(0.5);
    std::printf("  LCD: [%s] [%s]\n", get(e, in, "lcd1").c_str(), get(e, in, "lcd2").c_str());

    std::printf("LEDs:");
    for (const char* k : {"led_o1wave", "led_o2wave", "led_o2mod", "led_ftype", "led_lfo1", "led_lfo2", "led_timbre", "led_fx", "led_dist", "led_arp"})
        std::printf(" %s=%s", k + 4, get(e, in, k).c_str());
    std::printf("\n");
    CHECK(get(e, in, "led_o1wave") != "-" && get(e, in, "led_ftype") != "-", "OSC1 wave and filter type LEDs lit");
    e->set_param(in, "k_ftype", "1"); play(0.4);
    std::printf("  after FILTER TYPE key: %s\n", get(e, in, "led_ftype").c_str());
    std::printf("programs\n");
    std::printf("  %s | %s | %s\n", get(e, in, "patch_slot_1").c_str(), get(e, in, "patch_slot_2").c_str(), get(e, in, "patch_slot_16").c_str());
    CHECK(get(e, in, "patch_slot_1").find("A01 ") == 0 && get(e, in, "patch_slot_1").size() > 4, "A01 has a name");
    CHECK(get(e, in, "patch_slot_1_on") == "1", "A01 lit");

    std::printf("notes (C major, 2 s)\n");
    const uint8_t on[][3] = {{0x90, 60, 100}, {0x90, 64, 100}, {0x90, 67, 100}}, off[][3] = {{0x80, 60, 0}, {0x80, 64, 0}, {0x80, 67, 0}};
    size_t a = wav.size();
    for (auto& m : on) e->midi(in, m, 3);
    play(2.0);
    for (auto& m : off) e->midi(in, m, 3);
    play(1.5);
    int peak = 0; for (size_t k = a; k < wav.size(); ++k) peak = std::max(peak, std::abs(int(wav[k])));
    CHECK(peak > 1000, "chord audible (peak %d)", peak);

    std::printf("program select B03\n");
    e->set_param(in, "program", "18");
    play(0.5);
    std::printf("  LCD at 0.5 s: [%s]\n", get(e, in, "lcd1").c_str());
    play(1.5);
    std::printf("  LCD: [%s] [%s]  name: %s\n", get(e, in, "lcd1").c_str(), get(e, in, "lcd2").c_str(), get(e, in, "program_name").c_str());
    CHECK(get(e, in, "lcd1").find("B03") != std::string::npos, "LCD shows B03");
    CHECK(get(e, in, "bank_slot_2_on") == "1" && get(e, in, "patch_slot_3_on") == "1", "BANKS tiles follow (bank B, slot 3)");

    std::printf("favourites\n");
    const int favBefore = std::atoi(get(e, in, "favourite").c_str());
    e->set_param(in, "cut", "100");   // a knob tweak: the favourite keeps it
    play(0.3);
    e->set_param(in, "fav_save", "1"); e->set_param(in, "fav_save", "0");
    std::printf("  favourite now %s, name 0: %s\n", get(e, in, "favourite").c_str(), get(e, in, ("favourite:" + std::to_string(favBefore)).c_str()).c_str());
    CHECK(get(e, in, ("favourite:" + std::to_string(favBefore)).c_str()) != "-", "saved");
    e->set_param(in, "program", "0"); play(0.5);
    e->set_param(in, "favourite", std::to_string(favBefore).c_str()); play(0.5);
    std::printf("  LCD: [%s] [%s]  name: %s\n", get(e, in, "lcd1").c_str(), get(e, in, "lcd2").c_str(), get(e, in, "program_name").c_str());
    CHECK(get(e, in, "program_name").rfind("FAV ", 0) == 0, "favourite recalled");
    e->set_param(in, "fav_delete", "1"); e->set_param(in, "fav_delete", "0");
    CHECK(get(e, in, ("favourite:" + std::to_string(favBefore)).c_str()) == "-", "deleted again");

    std::printf("program-change stress: 20 programs, 0.3 s apart, a chord held\n");
    {
        const std::string before = get(e, in, "status");
        for (auto& m : on) e->midi(in, m, 3);
        for (int k = 0; k < 20; ++k) { e->set_param(in, "program", std::to_string((k * 7) % 128).c_str()); play(0.3); }
        for (auto& m : off) e->midi(in, m, 3);
        play(0.5);
        std::printf("  before: %s\n  after:  %s\n", before.c_str(), get(e, in, "status").c_str());
    }
    std::printf("state\n");
    const std::string st = get(e, in, "state");
    std::printf("  %zu chars: %.60s...\n", st.size(), st.c_str());
    CHECK(st.rfind("M2S1 ", 0) == 0 && st.size() > 500 && st.size() < 8000, "state fits the 8 KB chunk");
    e->set_param(in, "state", st.c_str()); play(0.5);
    CHECK(get(e, in, "state") == st, "state round trip");

    std::sort(times.begin(), times.end());
    long over = 0; for (double t : times) over += t > 2.902;
    double w4 = 0; for (size_t k = 0; k + 4 <= times.size(); k += 4) {}   // (per-512-frame windows below)
    std::printf("status at the end: %s\n", get(e, in, "status").c_str());
    std::printf("timing: %ld blocks, mean %.3f ms, p50 %.3f p99 %.3f p99.9 %.3f worst %.3f ms (budget 2.902 ms), over budget %ld\n",
                nblk, sum / nblk, times[times.size() / 2], times[times.size() * 99 / 100], times[times.size() * 999 / 1000], worst, over);
    if (argc > 2) if (FILE* f = std::fopen(argv[2], "wb")) {
        auto w32 = [&](uint32_t v) { std::fwrite(&v, 4, 1, f); }; auto w16 = [&](uint16_t v) { std::fwrite(&v, 2, 1, f); };
        std::fwrite("RIFF", 1, 4, f); w32(36 + uint32_t(wav.size() * 2)); std::fwrite("WAVEfmt ", 1, 8, f);
        w32(16); w16(1); w16(2); w32(44100); w32(44100 * 4); w16(4); w16(16); std::fwrite("data", 1, 4, f); w32(uint32_t(wav.size() * 2));
        std::fwrite(wav.data(), 2, wav.size(), f); std::fclose(f);
    }
    e->destroy(in);
    std::printf(fails ? "FAILED (%d)\n" : "PASSED\n", fails);
    return fails ? 1 : 0;
}
