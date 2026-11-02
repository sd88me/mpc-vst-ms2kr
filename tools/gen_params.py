#!/usr/bin/env python3
"""Write vst/params.json. The VST parameter index is the position in this list and saved projects bind to it:
only ever append (vst/params.lock, checked by gen_vst.py). Keys match src/dsp/ms2k_engine.cpp."""
import json, os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vst", "params.json")
params, secs = [], {}
def add(p, sec):
    params.append(p); secs.setdefault(sec, []).append(p["key"])
def poll(key, name, sec): add(dict(key=key, name=name, min=0, max=0, default=0, display="string", poll=True), sec)
def trig(key, name, sec, **kw): add(dict(key=key, name=name, min=0, max=1, default=0, momentary=True, **kw), sec)
def knob(key, name, sec): add(dict(key=key, name=name, min=0, max=1023, default=512, display="int"), sec)

PROGS = ["%s%02d" % ("ABCDEFGH"[i // 16], i % 16 + 1) for i in range(128)]
add(dict(key="program", name="PROGRAM", min=0, max=127, default=0, display="int"), "Browse")
poll("program_name", "NAME", "Browse")
trig("prog_prev", "PROG -", "Browse", step_of="program", step_delta=-1)
trig("prog_next", "PROG +", "Browse", step_of="program", step_delta=1)
poll("lcd1", "LCD 1", "Browse"); poll("lcd2", "LCD 2", "Browse")
trig("panic", "PANIC", "Browse")
add(dict(key="vol", name="VOLUME", min=0, max=1023, default=1023, display="int"), "Browse")
add(dict(key="out_level", name="OUTPUT %", min=0, max=100, default=100, display="int"), "Browse")
poll("status", "STATUS", "System")
for i in range(1, 9): trig("bank_slot_%d" % i, "BANK %s" % "ABCDEFGH"[i - 1], "Banks", display="string", poll=True)
for i in range(1, 17): trig("patch_slot_%d" % i, "PROG %d" % i, "Banks", display="string", poll=True)
add(dict(key="favourite", name="FAVOURITE", min=0, max=63, default=63, display="int"), "Banks")
trig("fav_save", "SAVE FAV", "Banks"); trig("fav_delete", "DEL FAV", "Banks")

KNOBS = [("o1c1", "OSC1 CTRL 1", "Oscillators"), ("o1c2", "OSC1 CTRL 2", "Oscillators"), ("o2semi", "OSC2 SEMI", "Oscillators"),
         ("o2tune", "OSC2 TUNE", "Oscillators"), ("mx1", "MIX OSC1", "Oscillators"), ("mx2", "MIX OSC2", "Oscillators"), ("mxn", "MIX NOISE", "Oscillators"),
         ("cut", "CUTOFF", "Filter & Amp"), ("res", "RESONANCE", "Filter & Amp"), ("eg1int", "EG1 INT", "Filter & Amp"), ("kbdtr", "KBD TRACK", "Filter & Amp"),
         ("lvl", "LEVEL", "Filter & Amp"), ("pan", "PAN", "Filter & Amp"),
         ("eg1a", "EG1 ATTACK", "Envelopes"), ("eg1d", "EG1 DECAY", "Envelopes"), ("eg1s", "EG1 SUSTAIN", "Envelopes"), ("eg1r", "EG1 RELEASE", "Envelopes"),
         ("eg2a", "EG2 ATTACK", "Envelopes"), ("eg2d", "EG2 DECAY", "Envelopes"), ("eg2s", "EG2 SUSTAIN", "Envelopes"), ("eg2r", "EG2 RELEASE", "Envelopes"),
         ("lfo1f", "LFO1 FREQ", "LFO & FX"), ("lfo2f", "LFO2 FREQ", "LFO & FX"), ("fxspd", "FX SPEED/TIME", "LFO & FX"), ("fxdep", "FX DEPTH/FDBK", "LFO & FX"),
         ("patch1", "PATCH 1", "Patch & Arp"), ("patch2", "PATCH 2", "Patch & Arp"), ("patch3", "PATCH 3", "Patch & Arp"), ("patch4", "PATCH 4", "Patch & Arp"),
         ("porta", "PORTAMENTO", "Oscillators"), ("tempo", "ARP TEMPO", "Patch & Arp"), ("gate", "ARP GATE", "Patch & Arp")]
for k, n, s in KNOBS: knob(k, n, s)
KEYS = [("k_o1wave", "OSC1 WAVE", "Oscillators"), ("k_o2wave", "OSC2 WAVE", "Oscillators"), ("k_o2mod", "OSC2 MOD", "Oscillators"),
        ("k_ftype", "FILTER TYPE", "Filter & Amp"), ("k_eg2gate", "EG2/GATE", "Filter & Amp"), ("k_dist", "DISTORTION", "Filter & Amp"),
        ("k_timbre", "TIMBRE SEL", "Edit"), ("k_mseqon", "MSEQ ON", "Patch & Arp"), ("k_mseqrec", "MSEQ REC", "Patch & Arp"),
        ("k_seqsel", "SEQ SELECT", "Patch & Arp"), ("k_kbd", "KEYBOARD", "Edit"), ("k_bankdn", "BANK/OCT -", "Edit"), ("k_bankup", "BANK/OCT +", "Edit"),
        ("k_arpon", "ARP ON", "Patch & Arp"), ("k_arplat", "ARP LATCH", "Patch & Arp"), ("k_arprng", "ARP RANGE", "Patch & Arp"), ("k_arptyp", "ARP TYPE", "Patch & Arp"),
        ("k_lfo1", "LFO1 WAVE", "LFO & FX"), ("k_lfo2", "LFO2 WAVE", "LFO & FX"), ("k_fxsel", "MOD/DELAY", "LFO & FX"),
        ("k_vpsel", "PATCH SEL", "Patch & Arp"), ("k_vpsrc", "PATCH SRC", "Patch & Arp"), ("k_vpdst", "PATCH DEST", "Patch & Arp"),
        ("k_curl", "CUR LEFT", "Edit"), ("k_curr", "CUR RIGHT", "Edit"), ("k_no", "- / NO", "Edit"), ("k_yes", "+ / YES", "Edit"),
        ("k_pagem", "PAGE -", "Edit"), ("k_pagep", "PAGE +", "Edit"), ("k_write", "WRITE", "Edit"), ("k_edit", "EDIT", "Edit"),
        ("k_global", "GLOBAL", "Edit"), ("k_exit", "EXIT", "Edit")]
for k, n, s in KEYS: trig(k, n, s, hold_ms=120)
# appended 2026-11-03 (saved projects bind by index): LED groups as text, the 16 program keys
LEDS = [("led_o1wave", "OSC1 WAVE"), ("led_o2wave", "OSC2 WAVE"), ("led_o2mod", "OSC2 MOD"), ("led_ftype", "FILTER TYPE"), ("led_timbre", "TIMBRE"),
        ("led_seq", "SEQ"), ("led_lfo1", "LFO1 WAVE"), ("led_lfo2", "LFO2 WAVE"), ("led_vpsel", "PATCH"), ("led_vpsrc", "SOURCE"), ("led_vpdst", "DEST"),
        ("led_eg2gate", "EG2/GATE"), ("led_dist", "DIST"), ("led_fx", "FX"), ("led_mseq", "MOD SEQ"), ("led_mrec", "SEQ REC"), ("led_arp", "ARP"),
        ("led_latch", "LATCH"), ("led_kbd", "KEYBOARD"), ("led_orig", "ORIGINAL")]
for k, n in LEDS: poll(k, n, "LEDs")
for i in range(1, 17): trig("k_pad%d" % i, "KEY %d" % i, "Keys", hold_ms=120)

ORDER = ["Browse", "Banks", "Oscillators", "Filter & Amp", "Envelopes", "LFO & FX", "Patch & Arp", "Edit", "System", "LEDs", "Keys"]
json.dump({"name": "MS2KR", "params": params, "sections": [{"label": s, "keys": secs[s]} for s in ORDER]}, open(OUT, "w"), indent=1)
print("params.json: %d params" % len(params))
