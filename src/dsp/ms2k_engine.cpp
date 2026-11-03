/* MS2000R for MPC (Gen2): the mpc-vst-plugins engine interface (wrapper/engine.h) on top of ms2000r-emu's Ms2kRunner.
 *
 * The machine is the real firmware on the emulated H8S/2350 + DSP56362 (src/ms2000r-emu); this file only drives it:
 *  - the machine thread (nice -5, as Osirus) boots the machine, then keeps an output ring ~kTarget frames ahead: the H8S
 *    runs there, the DSP on a thread of its own (Ms2kConfig::dspThread); render() only copies from the ring, so the
 *    firmware's uneven cost per block never reaches the host. Latency = the ring (kTarget / 44.1 kHz);
 *  - the machine's 48 kHz frames resampled to the wrapper's 44.1 kHz (4-point Hermite), int16 out;
 *  - MIDI through a single-producer FIFO; anything that reads or writes the machine runs on the machine thread;
 *  - MIDI in: channel messages moved to the machine's Global MIDI channel (read with a Device Inquiry at boot);
 *  - parameters = the physical panel (pots 0..1023 as on the unit, keys momentary), program select, BANKS tiles,
 *    favourites (whole 254-byte edit buffers, MPC's native program list), the LCD text;
 *  - the machine's memory (programs written with WRITE, GLOBAL) persists in <module dir>/memory/ like the unit's flash;
 *    the project state is the edit buffer + the panel, so a project brings its sound back on any machine memory.
 * ROMs (never shipped): <module dir>/roms/flash.bin and boot-362.bin (or boot-362.ms2000.bin). */
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#include <condition_variable>
#include <functional>
#include <future>
#include <sched.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

#include "core/ms2000_runner.h"
#include "core/h8s2350_emulator.h"
#include "core/dsp56362_emulator.h"
#include "core/flash_rom.h"
#include "core/lcd_gui.h"
#include "core/master_vr.h"

extern "C" {
#include "engine.h"
}

namespace {

constexpr int kOutRate = 44100, kMachineRate = 48000;
constexpr uint32_t kEditBuffer = 0x402E0Eu;    // DRAM: the 254-byte program being played (knob_follow.h)
constexpr uint32_t kProgramsAt = 0xA0400u;     // flash: 128 x 254-byte programs, A01..H16
constexpr int kProgLen = 254, kNameLen = 12;
constexpr int kFavSlots = 64;
constexpr int kRing = 8192, kTarget = 768, kChunk = 64;   // output frames; kTarget ~17.4 ms (as Osirus) = the least the ring is kept ahead
constexpr int kTargetMax = 3072;                           // ~70 ms: the most (when the host reads in big bursts)
// A program change (and a whole program sent as SysEx) makes the firmware upload DSP code: the JIT recompiles and one chunk takes
// ~17 ms on x86, ~45 ms on the A55 (measured 2026-11-03), more than the ring holds. So such a change waits until the ring is this
// far ahead (~58 ms; the machine runs faster than real time, so ~60 ms), then the stall eats the extra and the ring settles back.
constexpr int kBoost = 3584;   // ~81 ms. In MPC 2026-11-03 neither 2560 nor 3584 fully covers stepping programs every 0.5 s (8-14 dropouts in 20 steps); one step per 1.5 s: none
constexpr int kMidiFifo = 1024;
constexpr char kFavMagic[8] = {'M', '2', 'F', 'A', 'V', '1', '\n', 0};

// The panel: pots [mux][x] and keys [column][row] (ms2000r-emu source/plugin/panel_params.h, KOD-A30414/5)
struct Knob { const char* key; uint8_t mux, x; };
struct Key { const char* key; uint8_t col, row; };
const Knob kKnobs[] = {
    {"o1c1", 2, 6}, {"o1c2", 2, 1}, {"o2semi", 2, 7}, {"o2tune", 2, 0}, {"mx1", 2, 2}, {"mx2", 2, 4}, {"mxn", 2, 5},
    {"cut", 3, 7}, {"res", 3, 2}, {"eg1int", 3, 4}, {"kbdtr", 3, 6}, {"lvl", 3, 3}, {"pan", 3, 1},
    {"eg1a", 0, 4}, {"eg1d", 0, 6}, {"eg1s", 0, 2}, {"eg1r", 0, 0}, {"eg2a", 0, 7}, {"eg2d", 0, 1}, {"eg2s", 0, 5}, {"eg2r", 0, 3},
    {"lfo1f", 1, 4}, {"lfo2f", 1, 6}, {"fxspd", 1, 2}, {"fxdep", 1, 5},
    {"patch1", 1, 7}, {"patch2", 1, 0}, {"patch3", 1, 3}, {"patch4", 1, 1}, {"porta", 2, 3}, {"tempo", 3, 0}, {"gate", 3, 5},
};
const Key kKeys[] = {
    {"k_o1wave", 0, 7}, {"k_o2wave", 1, 1}, {"k_o2mod", 1, 0}, {"k_ftype", 1, 4}, {"k_eg2gate", 1, 7}, {"k_dist", 1, 6},
    {"k_timbre", 1, 2}, {"k_mseqon", 0, 6}, {"k_mseqrec", 1, 5}, {"k_seqsel", 0, 3}, {"k_kbd", 0, 4},
    {"k_bankdn", 2, 7}, {"k_bankup", 2, 6}, {"k_arpon", 2, 4}, {"k_arplat", 2, 3}, {"k_arprng", 2, 2}, {"k_arptyp", 2, 1},
    {"k_lfo1", 3, 5}, {"k_lfo2", 3, 4}, {"k_fxsel", 3, 3}, {"k_vpsel", 3, 2}, {"k_vpsrc", 3, 1}, {"k_vpdst", 3, 0},
    // editing keys (not in the desktop plugin's automation list; here they are the screen's own buttons)
    // (positions from upstream's vector_panel.h, KOD-A30414)
    {"k_curl", 4, 7}, {"k_curr", 4, 6}, {"k_no", 4, 5}, {"k_yes", 4, 4}, {"k_pagem", 4, 3}, {"k_pagep", 4, 2},
    {"k_write", 4, 1}, {"k_edit", 3, 7}, {"k_global", 3, 6}, {"k_exit", 4, 0},
    // the 16 program keys: 1-8 = column 6, 9-16 = column 5, row 7 - (n - 1) % 8
    {"k_pad1", 6, 7}, {"k_pad2", 6, 6}, {"k_pad3", 6, 5}, {"k_pad4", 6, 4}, {"k_pad5", 6, 3}, {"k_pad6", 6, 2}, {"k_pad7", 6, 1}, {"k_pad8", 6, 0},
    {"k_pad9", 5, 7}, {"k_pad10", 5, 6}, {"k_pad11", 5, 5}, {"k_pad12", 5, 4}, {"k_pad13", 5, 3}, {"k_pad14", 5, 2}, {"k_pad15", 5, 1}, {"k_pad16", 5, 0},
};

// LED groups as text (upstream vector_panel.h: led(ls, ld) beside each printed name). Several lit = joined with "+".
struct LedOpt { uint8_t ls, ld; const char* name; };
struct LedGroup { const char* key; const char* none; std::vector<LedOpt> opts; };
const LedGroup kLeds[] = {
    {"led_o1wave", "-", {{2, 4, "SAW"}, {3, 4, "SQU/PWM"}, {4, 4, "TRI"}, {5, 4, "SIN/CROSS"}, {2, 5, "VOX WAVE"}, {3, 5, "DWGS"}, {4, 5, "NOISE"}, {5, 5, "AUDIO IN"}}},
    {"led_o2wave", "-", {{3, 6, "SAW"}, {4, 6, "SQU"}, {5, 6, "TRI"}}},
    {"led_o2mod", "OFF", {{2, 7, "RING"}, {3, 7, "SYNC"}}},
    {"led_ftype", "-", {{2, 2, "24LPF"}, {3, 2, "12LPF"}, {4, 2, "12BPF"}, {2, 3, "12HPF"}}},
    {"led_timbre", "-", {{5, 3, "1"}, {5, 2, "2"}}},
    {"led_seq", "-", {{6, 1, "SEQ 1"}, {7, 0, "SEQ 2"}, {6, 0, "SEQ 3"}}},
    {"led_lfo1", "-", {{4, 3, "SAW"}, {7, 3, "SQU"}, {7, 4, "TRI"}, {7, 5, "S/H"}}},
    {"led_lfo2", "-", {{3, 3, "SAW"}, {7, 6, "SQU+"}, {7, 7, "SIN"}, {7, 8, "S/H"}}},
    {"led_vpsel", "-", {{0, 8, "PATCH 1"}, {1, 8, "PATCH 2"}, {2, 8, "PATCH 3"}, {3, 8, "PATCH 4"}}},
    {"led_vpsrc", "-", {{0, 9, "EG 1"}, {1, 9, "EG 2"}, {2, 9, "LFO 1"}, {3, 9, "LFO 2"}, {4, 9, "VELOCITY"}, {5, 9, "KBD TRACK"}, {6, 9, "MIDI 1"}, {7, 9, "MIDI 2"}}},
    {"led_vpdst", "-", {{0, 10, "PITCH"}, {1, 10, "OSC2 PITCH"}, {2, 10, "OSC1 CTRL1"}, {3, 10, "NOISE LVL"}, {4, 10, "CUTOFF"}, {5, 10, "AMP"}, {6, 10, "PAN"}, {7, 10, "LFO2 FREQ"}}},
    {"led_eg2gate", "EG 2", {{6, 4, "GATE"}}},
    {"led_dist", "OFF", {{6, 5, "ON"}}},
    {"led_fx", "MOD", {{6, 2, "DELAY"}}},
    {"led_mseq", "OFF", {{7, 1, "ON"}}},
    {"led_mrec", "OFF", {{6, 6, "REC"}}},
    {"led_arp", "OFF", {{6, 7, "ON"}}},
    {"led_latch", "OFF", {{5, 7, "ON"}}},
    {"led_kbd", "OFF", {{1, 11, "ON"}}},
    {"led_orig", "", {{4, 7, "ORIGINAL"}}},
};

std::atomic<bool> g_taken{false};   // the emulator has process-wide state: one machine per process

struct Inst {
    std::string dir, status = "starting";
    std::unique_ptr<MS2000::Ms2kRunner> runner;
    std::thread boot;
    std::atomic<int> phase{0};                  // 0 booting, 1 ready, 2 failed
    std::atomic<bool> quit{false};
    bool owner = false;
    int midiCh = 0;                             // the machine's Global MIDI channel, 0-based

    uint16_t knobs[4][8];
    bool keys[8][8] = {};
    float volume = 1.0f;                         // POWER/VOLUME (the panel pot, master_vr.h law)
    int outPct = 100;                            // OUTPUT LEVEL %

    std::vector<MS2000::Ms2kRunner::MidiEv> midiQ;     // machine thread: this chunk's events
    MS2000::Ms2kRunner::MidiEv midiFifo[kMidiFifo]; std::atomic<uint32_t> midiW{0}, midiR{0};
    int16_t ring[kRing * 2]; std::atomic<uint32_t> ringW{0}, ringR{0}; std::atomic<uint32_t> underruns{0};
    // the host's read pattern: frames taken in one burst (calls closer than 1 ms apart); the ring is kept that far ahead + margin
    std::chrono::steady_clock::time_point lastRead; uint32_t burst = 0; std::atomic<uint32_t> maxBurst{0}, target{uint32_t(kTarget)};
    std::atomic<uint32_t> minFill{0xFFFFFFFFu}; double worstProduceMs = 0; std::chrono::steady_clock::time_point logAt;
    std::mutex cmdMx; std::vector<std::function<void()>> cmds;
    std::vector<std::function<void()>> heavy;
    std::vector<MS2000::Ms2kRunner::MidiEv> inject;
    std::chrono::steady_clock::time_point boostUntil;  // the ring stays kBoost ahead until then (a SysEx program stalls ~100 ms after)   // machine thread: events for the next chunk, ahead of the FIFO's    // machine thread: changes that wait for the ring to be kBoost ahead
    std::mutex ledMx; float lit[8][12] = {}; std::chrono::steady_clock::time_point ledAt;
    std::chrono::steady_clock::time_point releaseAt[8][8] = {};   // machine thread: a key press lets go then
    std::mutex outMx; std::vector<uint8_t> outBytes;   // the firmware's MIDI OUT (Device Inquiry reply)

    // resampler: machine frames in, fractional read position
    std::vector<float> L, R, tmpL, tmpR; std::vector<uint8_t> tmpF;
    double pos = 1.0;

    // programs
    int program = 0;                             // the program last selected (A01 = 0)
    int favCount = 0, favCurrent = -1; char favName[kFavSlots][32]; uint8_t favData[kFavSlots][kProgLen];
    std::string pendingState;                    // a project restore that arrived while booting
};

std::string progLabel(int p) { char b[8]; std::snprintf(b, sizeof b, "%c%02d", 'A' + p / 16, p % 16 + 1); return b; }
bool exists(const std::string& p) { struct stat s; return ::stat(p.c_str(), &s) == 0; }

std::string trimName(const uint8_t* d)
{
    std::string n;
    for (int c = 0; c < kNameLen; ++c) n += (d[c] >= 0x20 && d[c] < 0x7F) ? char(d[c]) : ' ';
    while (!n.empty() && n.back() == ' ') n.pop_back();
    return n;
}

std::vector<uint8_t> encode7(const uint8_t* d, size_t n)
{
    std::vector<uint8_t> m;
    for (size_t i = 0; i < n; i += 7) {
        uint8_t hi = 0; const size_t k = std::min<size_t>(7, n - i);
        for (size_t j = 0; j < k; ++j) hi |= uint8_t(((d[i + j] >> 7) & 1) << j);
        m.push_back(hi);
        for (size_t j = 0; j < k; ++j) m.push_back(uint8_t(d[i + j] & 0x7F));
    }
    return m;
}

// ---- machine --------------------------------------------------------------------------------------------------------
void applyPanel(Inst* in)
{
    auto& e = in->runner->getEmulator();
    for (unsigned m = 0; m < 4; ++m) for (unsigned x = 0; x < 8; ++x) e.setPanelKnob(m, x, in->knobs[m][x]);
    for (unsigned c = 0; c < 8; ++c) for (unsigned r = 0; r < 8; ++r) if (in->keys[c][r]) e.setPanelSwitch(c, r, true);
}

// machine time without output (boot, waiting for an answer)
void runMachine(Inst* in, double seconds)
{
    const uint32_t chunk = 480;
    in->tmpL.resize(chunk); in->tmpR.resize(chunk); in->tmpF.resize(chunk);
    for (double t = 0; t < seconds && !in->quit.load(); t += double(chunk) / kMachineRate)
        in->runner->render(in->tmpL.data(), in->tmpR.data(), chunk, nullptr, 0, in->tmpF.data());
}

void sendSysex(Inst* in, std::vector<uint8_t> m) { in->runner->sendMIDIData(m.data(), m.size()); }

// MIDI from the wrapper (one producer: it never calls two engine functions at once) to the machine thread
void pushMidi(Inst* in, uint8_t a, uint8_t b, uint8_t c, uint8_t n)
{
    const uint32_t w = in->midiW.load(std::memory_order_relaxed);
    if (w - in->midiR.load(std::memory_order_acquire) >= uint32_t(kMidiFifo)) return;
    in->midiFifo[w % kMidiFifo] = {0, n, {a, b, c}};
    in->midiW.store(w + 1, std::memory_order_release);
}

// work on the machine: on the machine thread once it runs (before that, the boot thread owns the machine)
void post(Inst* in, std::function<void()> f) { std::lock_guard<std::mutex> l(in->cmdMx); in->cmds.push_back(std::move(f)); }
// a change that stalls the machine (program change, a program as SysEx): run once the ring is kBoost ahead
void postHeavy(Inst* in, std::function<void()> f) { post(in, [in, f] { in->heavy.push_back(f); }); }
template <class F> auto runSync(Inst* in, F f) -> decltype(f())
{
    auto task = std::make_shared<std::packaged_task<decltype(f())()>>(f);
    auto fut = task->get_future();
    post(in, [task] { (*task)(); });
    if (fut.wait_for(std::chrono::milliseconds(500)) != std::future_status::ready) return decltype(f())();
    return fut.get();
}

void loadEditBuffer(Inst* in, const uint8_t* prog)   // CURRENT PROGRAM DATA DUMP (40) into the edit buffer
{
    std::vector<uint8_t> m = {0xF0, 0x42, uint8_t(0x30 | in->midiCh), 0x58, 0x40};
    const auto enc = encode7(prog, kProgLen); m.insert(m.end(), enc.begin(), enc.end()); m.push_back(0xF7);
    sendSysex(in, m);
}

void selectProgram(Inst* in, int p)
{
    if (p < 0 || p > 127) return;
    in->program = p; in->favCurrent = -1;
    if (in->phase.load() != 1) return;
    const uint8_t pc[2] = {uint8_t(0xC0 | in->midiCh), uint8_t(p)};
    postHeavy(in, [in, pc] { in->inject.push_back({0, 2, {pc[0], pc[1], 0}}); });
}

std::string memImage(Inst* in) { return in->dir + "/memory/flash_state.bin"; }
std::string memMask(Inst* in) { return in->dir + "/memory/flash_state.sectors"; }

void saveMemory(Inst* in)
{
    if (!in->runner) return;
    auto& f = in->runner->getEmulator().getFlashROM();
    if (!f.dirtySectors()) return;
    ::mkdir((in->dir + "/memory").c_str(), 0755);
    f.saveState(memImage(in), memMask(in));
}

/* Big/little CPUs (Live III: cores 0-3 at 1.8 GHz, 4-7 at 2.4 GHz). MPC pins its real-time audio threads to the fast cores,
 * the last one carrying "Audio Processing"; left unpinned, the two emulator threads wandered between all cores, ran on the slow
 * ones part of the time and dropped out (measured 2026-11-03: ring empty in most 5 s windows; pinned to 4-6 by hand: none).
 * So: the fastest cores, without the highest-numbered one when there are three or more. Same-speed CPUs: left alone. */
std::vector<int> fastCores()
{
    long best = 0; long f[64]; int n = 0;
    for (; n < 64; ++n) {
        char p[96]; std::snprintf(p, sizeof p, "/sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq", n);
        FILE* fp = std::fopen(p, "r");
        if (!fp) break;
        if (std::fscanf(fp, "%ld", &f[n]) != 1) f[n] = 0;
        std::fclose(fp);
        best = std::max(best, f[n]);
    }
    std::vector<int> fast;
    bool mixed = false;
    for (int i = 0; i < n; ++i) { if (f[i] == best) fast.push_back(i); else mixed = true; }
    if (!mixed || fast.empty()) return {};
    if (fast.size() >= 3) fast.pop_back();
    return fast;
}

bool pinTo(int core) { cpu_set_t set; CPU_ZERO(&set); CPU_SET(core, &set); return sched_setaffinity(0, sizeof set, &set) == 0; }

/* The two emulator threads hand work to each other all the time (the H8S waits for the DSP and the other way round), so they
 * must not share a core: within one shared mask they often did, and a program change then ran short of time (measured in MPC
 * 2026-11-03: 113 dropouts stepping 20 programs at 2/s). The DSP thread (started from the boot thread) gets the first fast
 * core, the machine thread the last; MPC's busiest worker and "Audio Processing" stay out of the way as far as they can. */
void pinToFastCores() { const auto f = fastCores(); if (!f.empty()) pinTo(f.front()); }   // before the runner starts the DSP thread
void pinMachineThread()
{
    const auto f = fastCores();
    if (f.size() < 2) return;
    pinTo(f.back());
    std::fprintf(stderr, "[ms2kr] DSP thread on core %d, machine thread on core %d\n", f.front(), f.back());
}

void applyState(Inst* in, const std::string& s);
void produce(Inst* in);
void machineLoop(Inst* in);

void bootThread(Inst* in)
{
    // as Osirus: never touch threads that are not ours; the DSP thread the runner starts inherits this nice value
    setpriority(PRIO_PROCESS, id_t(syscall(SYS_gettid)), -5);
    pinToFastCores();   // and this affinity
    const std::string roms = in->dir + "/roms";
    std::string boot = roms + "/boot-362.ms2000.bin";
    if (!exists(boot)) boot = roms + "/boot-362.bin";
    if (!exists(roms + "/flash.bin") || !exists(boot)) {
        in->status = "ROMs missing: put flash.bin and boot-362.bin in " + roms;
        in->phase = 2; return;
    }
    ::setenv("MS2K_DSPROM", boot.c_str(), 1);    // the core looks for it by relative path otherwise
    ::setenv("MS2K_MODEL", "R", 0);              // the rack: PA5 strap low

    MS2000::Ms2kConfig cfg;
    cfg.romPath = roms + "/flash.bin";
    cfg.cpuCyclesPerTick = 20000;
    cfg.sampleRate = kMachineRate;
    cfg.quietBoot = true;
    cfg.audio.enabled = false;
    cfg.enableMidiSmokeTest = false;
    cfg.dspThread = true;
    cfg.flashStateLoad = false; cfg.flashStateSave = false;   // relative paths in the runner: this file does it
    if (FILE* f = std::fopen(memMask(in).c_str(), "r")) {      // the machine's memory from earlier sessions
        unsigned mask = 0;
        if (std::fscanf(f, "%x", &mask) == 1 && mask) {
            std::vector<uint8_t> img(1u << 20, 0xFF);
            if (FILE* g = std::fopen(memImage(in).c_str(), "rb")) {
                if (std::fread(img.data(), 1, img.size(), g) == img.size()) { cfg.flashStateMask = mask; cfg.flashStateImage = std::move(img); }
                std::fclose(g);
            }
        }
        std::fclose(f);
    }
    MS2000::Ms2kGuiHooks hooks;
    hooks.logFn = [](const char*) {};
    in->status = "booting";
    in->runner = std::make_unique<MS2000::Ms2kRunner>(cfg, hooks);
    if (!in->runner->init() || !in->runner->startManual()) { in->status = "the machine did not start"; in->phase = 2; return; }
    pinMachineThread();   // the DSP thread has started on the first fast core: this thread moves to its own
    in->runner->getEmulator().setMidiOutSink([in](uint8_t b) { std::lock_guard<std::mutex> l(in->outMx); if (in->outBytes.size() < 4096) in->outBytes.push_back(b); });
    applyPanel(in);
    runMachine(in, 4.0);                                    // boot: the DSP program upload, the splash

    // Global MIDI channel: Device Inquiry -> F0 7E 0g 06 02 42 58 ...
    { std::lock_guard<std::mutex> l(in->outMx); in->outBytes.clear(); }
    sendSysex(in, {0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7});
    for (int i = 0; i < 20 && !in->quit.load(); ++i) {
        runMachine(in, 0.05);
        std::lock_guard<std::mutex> l(in->outMx);
        const auto& o = in->outBytes;
        for (size_t k = 0; k + 4 < o.size(); ++k)
            if (o[k] == 0xF0 && o[k + 1] == 0x7E && o[k + 3] == 0x06 && o[k + 4] == 0x02) { in->midiCh = o[k + 2] & 0x0F; i = 99; break; }
    }
    if (!in->pendingState.empty()) { applyState(in, in->pendingState); in->pendingState.clear(); runMachine(in, 0.3); }
    in->pos = 1.0; in->L.assign(4, 0.0f); in->R.assign(4, 0.0f);
    while (in->ringW.load() - in->ringR.load() < in->target.load() && !in->quit.load()) produce(in);   // start full
    char b[64]; std::snprintf(b, sizeof b, "ready (MIDI ch %d)", in->midiCh + 1);
    in->status = b;
    in->phase = 1;
    machineLoop(in);
}

// ---- favourites (<module dir>/favourites.dat: magic, then records of 32 name bytes + 254 program bytes) -------------
std::string favPath(Inst* in) { return in->dir + "/favourites.dat"; }

void favLoad(Inst* in)
{
    in->favCount = 0;
    FILE* f = std::fopen(favPath(in).c_str(), "rb");
    if (!f) return;
    char magic[8];
    if (std::fread(magic, 1, 8, f) == 8 && std::memcmp(magic, kFavMagic, 8) == 0)
        while (in->favCount < kFavSlots && std::fread(in->favName[in->favCount], 1, 32, f) == 32
               && std::fread(in->favData[in->favCount], 1, kProgLen, f) == size_t(kProgLen)) in->favCount++;
    std::fclose(f);
}

bool favWrite(Inst* in)
{
    const std::string p = favPath(in), tmp = p + ".tmp";
    FILE* f = std::fopen(tmp.c_str(), "wb");
    if (!f) return false;
    bool ok = std::fwrite(kFavMagic, 1, 8, f) == 8;
    for (int i = 0; ok && i < in->favCount; ++i)
        ok = std::fwrite(in->favName[i], 1, 32, f) == 32 && std::fwrite(in->favData[i], 1, kProgLen, f) == size_t(kProgLen);
    ok = (std::fclose(f) == 0) && ok;
    return ok && std::rename(tmp.c_str(), p.c_str()) == 0;
}

void readEditBuffer(Inst* in, uint8_t* out)
{
    auto& e = in->runner->getEmulator();
    for (int i = 0; i < kProgLen; ++i) out[i] = e.peekExternal(kEditBuffer + uint32_t(i));
}

void favSave(Inst* in)
{
    if (in->phase.load() != 1 || in->favCount >= kFavSlots) return;
    std::array<uint8_t, kProgLen> eb = runSync(in, [in] { std::array<uint8_t, kProgLen> a{}; readEditBuffer(in, a.data()); return a; });
    const uint8_t* d = eb.data();
    if (std::all_of(eb.begin(), eb.end(), [](uint8_t v) { return v == 0; })) return;   // no answer
    for (int i = 0; i < in->favCount; ++i) if (std::memcmp(in->favData[i], d, kProgLen) == 0) return;   // already there
    const int i = in->favCount;
    std::memset(in->favName[i], 0, 32);
    const std::string nm = trimName(d);
    std::snprintf(in->favName[i], 31, "%s", nm.empty() ? ("Favourite " + std::to_string(i + 1)).c_str() : nm.c_str());
    std::memcpy(in->favData[i], d, kProgLen);
    in->favCount++;
    if (!favWrite(in)) in->favCount--;
    else in->favCurrent = i;
}

void favDelete(Inst* in)
{
    const int d = in->favCurrent;
    if (d < 0 || d >= in->favCount) return;
    for (int i = d; i + 1 < in->favCount; ++i) { std::memcpy(in->favName[i], in->favName[i + 1], 32); std::memcpy(in->favData[i], in->favData[i + 1], kProgLen); }
    in->favCount--; favWrite(in); in->favCurrent = -1;
}

// ---- project state: "M2S1 <program> <volume> <32 knobs hex> <254-byte edit buffer hex>" --------------------------------
std::string makeState(Inst* in)
{
    std::string s = "M2S1 " + std::to_string(in->program) + " " + std::to_string(int(in->volume * 1000.0f + 0.5f)) + " ";
    char b[8];
    for (const auto& k : kKnobs) { std::snprintf(b, sizeof b, "%03X", in->knobs[k.mux][k.x]); s += b; }
    s += " ";
    if (in->phase.load() == 1) {
        const auto eb = runSync(in, [in] { std::array<uint8_t, kProgLen> a{}; readEditBuffer(in, a.data()); return a; });
        const uint8_t* d = eb.data();
        for (int i = 0; i < kProgLen; ++i) { std::snprintf(b, sizeof b, "%02X", d[i]); s += b; }
    }
    return s;
}

void applyState(Inst* in, const std::string& s)
{
    if (s.compare(0, 5, "M2S1 ") != 0) return;
    int prog = 0, vol = 1000; char kn[200] = {}, eb[600] = {};
    const int n = std::sscanf(s.c_str() + 5, "%d %d %199s %599s", &prog, &vol, kn, eb);
    if (n < 3) return;
    in->volume = std::clamp(vol, 0, 1000) / 1000.0f;
    for (size_t i = 0; i < std::size(kKnobs) && (i + 1) * 3 <= std::strlen(kn); ++i) {
        char h[4] = {kn[i * 3], kn[i * 3 + 1], kn[i * 3 + 2], 0};
        in->knobs[kKnobs[i].mux][kKnobs[i].x] = uint16_t(std::min(1023L, std::strtol(h, nullptr, 16)));
    }
    in->program = std::clamp(prog, 0, 127);
    if (!in->runner || in->phase.load() == 0) return;   // booting: bootThread applies pendingState
    applyPanel(in);
    in->runner->sendMIDIData(std::vector<uint8_t>{uint8_t(0xC0 | in->midiCh), uint8_t(in->program)}.data(), 2);
    if (n == 4 && std::strlen(eb) == size_t(kProgLen) * 2) {   // the sound as it was, knob tweaks included
        uint8_t d[kProgLen];
        for (int i = 0; i < kProgLen; ++i) { char h[3] = {eb[i * 2], eb[i * 2 + 1], 0}; d[i] = uint8_t(std::strtol(h, nullptr, 16)); }
        loadEditBuffer(in, d);
    }
}

// ---- engine interface -----------------------------------------------------------------------------------------------
void* eCreate(const char* dir)
{
    auto* in = new Inst;
    in->dir = dir && *dir ? dir : ".";
    for (auto& m : in->knobs) for (auto& v : m) v = 512;
    favLoad(in);
    if (g_taken.exchange(true)) { in->status = "only one MS2000R per MPC"; in->phase = 2; return in; }
    in->owner = true;
    in->boot = std::thread(bootThread, in);
    return in;
}

void eDestroy(void* p)
{
    auto* in = static_cast<Inst*>(p);
    in->quit = true;
    if (in->boot.joinable()) in->boot.join();
    if (in->runner) { saveMemory(in); in->runner->getEmulator().setMidiOutSink(nullptr); in->runner->stop(); in->runner.reset(); }
    if (in->owner) g_taken = false;
    delete in;
}

void eMidi(void* p, const uint8_t* m, int n)
{
    auto* in = static_cast<Inst*>(p);
    if (in->phase.load() != 1 || n < 1 || n > 3 || m[0] < 0x80 || m[0] >= 0xF0) return;
    if ((m[0] & 0xF0) == 0xC0 && n > 1) { in->program = m[1] & 0x7F; in->favCurrent = -1; }
    pushMidi(in, uint8_t((m[0] & 0xF0) | in->midiCh), n > 1 ? m[1] : uint8_t(0), n > 2 ? m[2] : uint8_t(0), uint8_t(n));
}

int slotKey(const char* key, const char* prefix, int count, bool* on)
{
    const size_t n = std::strlen(prefix);
    if (std::strncmp(key, prefix, n) != 0) return 0;
    char* end = nullptr; const long v = std::strtol(key + n, &end, 10);
    if (v < 1 || v > count) return 0;
    *on = std::strcmp(end, "_on") == 0;
    return (*on || *end == 0) ? int(v) : 0;
}

void eSet(void* p, const char* key, const char* val)
{
    auto* in = static_cast<Inst*>(p);
    const bool live = in->phase.load() == 1;
    const int iv = std::atoi(val);
    bool on = false; int n;
    if ((n = slotKey(key, "bank_slot_", 8, &on))) { if (!on && iv) selectProgram(in, (n - 1) * 16 + in->program % 16); return; }
    if ((n = slotKey(key, "patch_slot_", 16, &on))) { if (!on && iv) selectProgram(in, (in->program / 16) * 16 + n - 1); return; }
    if (!std::strcmp(key, "program")) { if (iv != in->program || in->favCurrent >= 0) selectProgram(in, iv); return; }
    if (!std::strcmp(key, "prog_prev")) { if (iv) selectProgram(in, (in->program + 127) % 128); return; }
    if (!std::strcmp(key, "prog_next")) { if (iv) selectProgram(in, (in->program + 1) % 128); return; }
    if (!std::strcmp(key, "fav_save")) { if (iv) favSave(in); return; }
    if (!std::strcmp(key, "fav_delete")) { if (iv) favDelete(in); return; }
    if (!std::strcmp(key, "favourite")) {
        if (iv >= 0 && iv < in->favCount && live) {
            std::vector<uint8_t> d(in->favData[iv], in->favData[iv] + kProgLen);
            postHeavy(in, [in, d] { loadEditBuffer(in, d.data()); });
            in->favCurrent = iv;
        }
        return;
    }
    if (!std::strcmp(key, "panic")) {
        if (iv && live) { pushMidi(in, uint8_t(0xB0 | in->midiCh), 123, 0, 3); pushMidi(in, uint8_t(0xB0 | in->midiCh), 120, 0, 3); }
        return;
    }
    if (!std::strcmp(key, "out_level")) { in->outPct = std::clamp(iv, 0, 100); return; }
    if (!std::strcmp(key, "vol")) { in->volume = std::clamp(iv, 0, 1023) / 1023.0f; return; }
    if (!std::strcmp(key, "state")) {
        if (live) { std::string v = val; postHeavy(in, [in, v] { applyState(in, v); }); }
        else { applyState(in, val); in->pendingState = val; }   // panel + program now, the rest once booted
        return;
    }
    for (const auto& k : kKnobs) if (!std::strcmp(key, k.key)) {
        in->knobs[k.mux][k.x] = uint16_t(std::clamp(iv, 0, 1023));
        if (live) in->runner->getEmulator().setPanelKnob(k.mux, k.x, in->knobs[k.mux][k.x]);
        return;
    }
    // a key: the wrapper sends the press only (momentary); the machine thread lets go 100 ms later, long enough for the
    // firmware's key scan to see it
    for (const auto& k : kKeys) if (!std::strcmp(key, k.key)) {
        if (iv && live) {
            const unsigned c = k.col, r = k.row;
            post(in, [in, c, r] { in->runner->getEmulator().setPanelSwitch(c, r, true);
                                  in->releaseAt[c][r] = std::chrono::steady_clock::now() + std::chrono::milliseconds(100); });
        }
        return;
    }
}

const char* progName(Inst* in, int p, char* out, size_t n)   // the machine's memory, writes included
{
    if (!in->runner || in->phase.load() != 1) { std::snprintf(out, n, "%s", progLabel(p).c_str()); return out; }
    const uint8_t* d = in->runner->getEmulator().getFlashROM().data() + kProgramsAt + uint32_t(p) * kProgLen;
    std::snprintf(out, n, "%s %s", progLabel(p).c_str(), trimName(d).c_str());
    return out;
}

int eGet(void* p, const char* key, char* buf, int len)
{
    auto* in = static_cast<Inst*>(p);
    const bool live = in->phase.load() == 1;
    char t[64]; bool on = false; int n;
    if ((n = slotKey(key, "bank_slot_", 8, &on))) {
        if (on) return std::snprintf(buf, len, "%d", (n - 1) == in->program / 16 && in->favCurrent < 0 ? 1 : 0);
        return std::snprintf(buf, len, "BANK %c", 'A' + n - 1);
    }
    if ((n = slotKey(key, "patch_slot_", 16, &on))) {
        const int pr = (in->program / 16) * 16 + n - 1;
        if (on) return std::snprintf(buf, len, "%d", pr == in->program && in->favCurrent < 0 ? 1 : 0);
        return std::snprintf(buf, len, "%s", progName(in, pr, t, sizeof t));
    }
    if (!std::strcmp(key, "state")) return std::snprintf(buf, len, "%s", makeState(in).c_str());
    if (!std::strcmp(key, "display_rev")) {   // HAS_DISPLAY_REV: changes whenever the LCD, the program or the status does
        uint32_t h = 2166136261u;
        auto mix = [&](const char* z) { for (; *z; ++z) h = (h ^ uint8_t(*z)) * 16777619u; };
        if (live) { const auto s = in->runner->getLcdGuiSnapshot(); mix(s.line0); mix(s.line1); }
        mix(in->status.c_str());
        { std::lock_guard<std::mutex> l(in->ledMx); for (auto& r : in->lit) for (float v : r) h = (h ^ uint32_t(v > 0.25f)) * 16777619u; }
        h ^= uint32_t(in->program * 131 + in->favCurrent * 7 + in->favCount);
        return std::snprintf(buf, len, "%u", h & 0x7FFFFFFFu);
    }
    if (!std::strcmp(key, "status")) {
        if (live) return std::snprintf(buf, len, "%s, dropouts %u", in->status.c_str(), in->underruns.load());
        return std::snprintf(buf, len, "%s", in->status.c_str());
    }
    if (!std::strcmp(key, "program")) return std::snprintf(buf, len, "%d", in->program);
    if (!std::strcmp(key, "program_display")) return std::snprintf(buf, len, "%s", progLabel(in->program).c_str());
    if (!std::strcmp(key, "program_name")) {
        if (in->favCurrent >= 0) return std::snprintf(buf, len, "FAV %s", in->favName[in->favCurrent]);
        return std::snprintf(buf, len, "%s", progName(in, in->program, t, sizeof t));
    }
    if (!std::strcmp(key, "lcd1") || !std::strcmp(key, "lcd2")) {
        if (!live) return std::snprintf(buf, len, "%s", key[3] == '1' ? "MS2000R" : in->status.c_str());
        const auto s = in->runner->getLcdGuiSnapshot();
        return std::snprintf(buf, len, "%.16s", key[3] == '1' ? s.line0 : s.line1);
    }
    for (const auto& g : kLeds) if (!std::strcmp(key, g.key)) {
        std::string t;
        { std::lock_guard<std::mutex> l(in->ledMx);
          for (const auto& o : g.opts) if (in->lit[o.ls][o.ld] > 0.25f) { if (!t.empty()) t += "+"; t += o.name; } }
        return std::snprintf(buf, len, "%s", t.empty() ? g.none : t.c_str());
    }
    for (const auto& g : kLeds) if (!std::strcmp(key, g.key)) {
        std::string t;
        { std::lock_guard<std::mutex> l(in->ledMx);
          for (const auto& o : g.opts) if (in->lit[o.ls][o.ld] > 0.25f) { if (!t.empty()) t += "+"; t += o.name; } }
        return std::snprintf(buf, len, "%s", t.empty() ? g.none : t.c_str());
    }
    if (!std::strcmp(key, "favourite"))
        return std::snprintf(buf, len, "%d", in->favCurrent >= 0 ? in->favCurrent : std::min(in->favCount, kFavSlots - 1));
    if (!std::strncmp(key, "favourite:", 10)) {
        const int i = std::atoi(key + 10);
        return std::snprintf(buf, len, "%s", i >= 0 && i < in->favCount ? in->favName[i] : "-");
    }
    if (!std::strcmp(key, "out_level")) return std::snprintf(buf, len, "%d", in->outPct);
    if (!std::strcmp(key, "vol")) return std::snprintf(buf, len, "%d", int(in->volume * 1023.0f + 0.5f));
    for (const auto& k : kKnobs) if (!std::strcmp(key, k.key)) return std::snprintf(buf, len, "%d", in->knobs[k.mux][k.x]);
    for (const auto& k : kKeys) if (!std::strcmp(key, k.key)) return std::snprintf(buf, len, "0");
    return -1;
}


inline float hermite(float xm1, float x0, float x1, float x2, float t)
{
    const float c = (x1 - xm1) * 0.5f, v = x0 - x1, w = c + v, a = w + v + (x2 - x0) * 0.5f, b = w + a;
    return ((a * t - b) * t + c) * t + x0;
}

// machine thread: kChunk more output frames into the ring
void produce(Inst* in)
{
    constexpr double step = double(kMachineRate) / kOutRate;
    in->midiQ.swap(in->inject); in->inject.clear();
    uint32_t r = in->midiR.load(std::memory_order_relaxed);
    for (const uint32_t w = in->midiW.load(std::memory_order_acquire); r != w; ++r) {
        const auto ev = in->midiFifo[r % kMidiFifo];
        if ((ev.data[0] & 0xF0) == 0xC0) {   // what follows it waits with it, in order
            if (in->heavy.empty()) { const auto pc = ev; in->heavy.push_back([in, pc] { in->inject.push_back(pc); }); ++r; }
            break;
        }
        in->midiQ.push_back(ev);
    }
    in->midiR.store(r, std::memory_order_release);
    const double endPos = in->pos + step * kChunk;
    const int need = int(std::ceil(endPos)) + 3 - int(in->L.size());
    if (need > 0) {
        in->tmpL.resize(size_t(need)); in->tmpR.resize(size_t(need)); in->tmpF.resize(size_t(need));
        in->runner->render(in->tmpL.data(), in->tmpR.data(), uint32_t(need), in->midiQ.data(), in->midiQ.size(), in->tmpF.data());
        in->L.insert(in->L.end(), in->tmpL.begin(), in->tmpL.end());
        in->R.insert(in->R.end(), in->tmpR.begin(), in->tmpR.end());
    } else for (auto& e : in->midiQ) in->runner->sendMIDIData(e.data, e.len);
    const float g = ms2kMasterVrGain(in->volume) * float(in->outPct) / 100.0f * 32767.0f;
    uint32_t w = in->ringW.load(std::memory_order_relaxed);
    for (int i = 0; i < kChunk; ++i, ++w) {
        const int k = int(in->pos); const float t = float(in->pos - k);
        const float l = hermite(in->L[size_t(k - 1)], in->L[size_t(k)], in->L[size_t(k + 1)], in->L[size_t(k + 2)], t);
        const float r = hermite(in->R[size_t(k - 1)], in->R[size_t(k)], in->R[size_t(k + 1)], in->R[size_t(k + 2)], t);
        in->ring[(w % kRing) * 2] = int16_t(std::clamp(l * g, -32768.0f, 32767.0f));
        in->ring[(w % kRing) * 2 + 1] = int16_t(std::clamp(r * g, -32768.0f, 32767.0f));
        in->pos += step;
    }
    in->ringW.store(w, std::memory_order_release);
    const int drop = int(in->pos) - 1;   // keep one frame of history
    if (drop > 0) {
        in->L.erase(in->L.begin(), in->L.begin() + drop); in->R.erase(in->R.begin(), in->R.begin() + drop);
        in->pos -= drop;
    }
}

void machineLoop(Inst* in)
{
    while (!in->quit.load(std::memory_order_relaxed)) {
        std::vector<std::function<void()>> c;
        { std::lock_guard<std::mutex> l(in->cmdMx); c.swap(in->cmds); }
        for (auto& f : c) f();
        const uint32_t fill = in->ringW.load(std::memory_order_relaxed) - in->ringR.load(std::memory_order_acquire);
        if (!in->heavy.empty() && fill >= uint32_t(kBoost)) {   // far enough ahead: the change, and its stall, now
            auto h = std::move(in->heavy.front()); in->heavy.erase(in->heavy.begin()); h();
            in->boostUntil = std::chrono::steady_clock::now() + std::chrono::milliseconds(400);
        }
        const bool boosting = !in->heavy.empty() || std::chrono::steady_clock::now() < in->boostUntil;
        const uint32_t want = boosting ? uint32_t(kBoost) : in->target.load(std::memory_order_relaxed);
        if (fill < want) {
            const auto t0 = std::chrono::steady_clock::now();
            produce(in);
            in->worstProduceMs = std::max(in->worstProduceMs, std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count());
        }
        const auto now = std::chrono::steady_clock::now();
        if (now - in->logAt > std::chrono::seconds(5)) {   // to MPC's log (journalctl -u acvs | grep ms2kr)
            in->logAt = now;
            std::fprintf(stderr, "[ms2kr] dropouts %u, ring min %u / target %u frames, host burst max %u, slowest %d-frame chunk %.2f ms\n",
                         in->underruns.load(), in->minFill.exchange(0xFFFFFFFFu), in->target.load(), in->maxBurst.load(), kChunk, in->worstProduceMs);
            in->worstProduceMs = 0;
        }
        for (unsigned c = 0; c < 8; ++c) for (unsigned r = 0; r < 8; ++r)
            if (in->releaseAt[c][r].time_since_epoch().count() && now >= in->releaseAt[c][r]) {
                in->runner->getEmulator().setPanelSwitch(c, r, false); in->releaseAt[c][r] = {};
            }
        if (now - in->ledAt > std::chrono::milliseconds(30)) {
            in->ledAt = now;
            const auto leds = in->runner->getEmulator().panelLeds();
            std::lock_guard<std::mutex> l(in->ledMx);
            std::memcpy(in->lit, leds.lit, sizeof in->lit);
        }
        else std::this_thread::sleep_for(std::chrono::microseconds(500));
    }
    std::vector<std::function<void()>> c;   // answer what is still waiting (runSync callers)
    { std::lock_guard<std::mutex> l(in->cmdMx); c.swap(in->cmds); }
    for (auto& f : c) f();
}

void eRender(void* p, int16_t* out, int frames)
{
    auto* in = static_cast<Inst*>(p);
    uint32_t r = in->ringR.load(std::memory_order_relaxed);
    const uint32_t avail = in->ringW.load(std::memory_order_acquire) - r;
    if (in->phase.load() == 1) {
        const auto now = std::chrono::steady_clock::now();
        in->burst = (now - in->lastRead < std::chrono::milliseconds(1)) ? in->burst + uint32_t(frames) : uint32_t(frames);
        in->lastRead = now;
        if (in->burst > in->maxBurst.load(std::memory_order_relaxed)) {
            in->maxBurst.store(in->burst, std::memory_order_relaxed);
            in->target.store(std::min<uint32_t>(kTargetMax, std::max<uint32_t>(kTarget, in->burst * 2 + 256)), std::memory_order_relaxed);
        }
        if (avail < in->minFill.load(std::memory_order_relaxed)) in->minFill.store(avail, std::memory_order_relaxed);
    }
    const int n = in->phase.load() == 1 ? int(std::min<uint32_t>(avail, uint32_t(frames))) : 0;
    for (int i = 0; i < n; ++i, ++r) { out[2 * i] = in->ring[(r % kRing) * 2]; out[2 * i + 1] = in->ring[(r % kRing) * 2 + 1]; }
    if (n < frames) {
        std::memset(out + 2 * n, 0, sizeof(int16_t) * 2 * size_t(frames - n));
        if (in->phase.load() == 1) in->underruns.fetch_add(1, std::memory_order_relaxed);
    }
    in->ringR.store(r, std::memory_order_release);
}

const mpc_engine_t kEngine = {eCreate, eDestroy, eMidi, eSet, eGet, eRender, nullptr, nullptr};

}   // namespace

extern "C" const mpc_engine_t* mpc_engine(void) { return &kEngine; }
