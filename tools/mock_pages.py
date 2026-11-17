#!/usr/bin/env python3
"""Mock-ups of the MS2KR skin pages (static art plus sample live values) for review: docs/skin-preview/<page>.png.
    tools/mock_pages.py [play] [filter]"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
import ms2k_art as A

OUT = os.path.join(A.ROOT, "docs", "skin-preview")
W, H = 1280, 628
DEVICE_TEXT = 0.64          # the MPC draws a Label's font at about this fraction of its height
_cache = {}


def knob_frame(size, t):
    if "strip" not in _cache:
        t0 = time.time()
        _cache["strip"] = A.knob_strip(size, 101)
        print("knob strip %.1fs" % (time.time() - t0))
    f = int(round(t * 100))
    return _cache["strip"].crop((0, f * size, size, (f + 1) * size))


def knob(im, cx, cy, label, t=0.5, pill=None, size=84, value=None):
    A.ticks(im, cx, cy, 46)
    im.alpha_composite(knob_frame(size, t), (cx - size // 2, cy - size // 2))
    A.caption(im, cx, cy - 74, label, 15, width=130)
    if pill:
        A.pill(im, cx, cy - 56, pill, 11, 120)


def live(im, cx, cy, text, h=22, colour=(255, 255, 255), bold=True, anchor="mm"):
    """sample live text as the device would draw it"""
    f = A.F(max(8, int(h * DEVICE_TEXT)), bold)
    ImageDraw.Draw(im).text((cx, cy), text, font=f, fill=colour + (255,), anchor=anchor)


def header(im, program="A01 Stab Saw"):
    A.wordmark(im, 26, 12)
    A.lcd(im, 330, 10, 770, 98)
    live(im, 346, 38, "Stab Saw", 34, A.LCD_INK, anchor="lm")
    live(im, 346, 72, "A01  Prog Select", 34, A.LCD_INK, anchor="lm")
    A.section(im, 800, 22, 1264, 98, "PROGRAM")
    for x, k in ((836, "-"), (1228, "+")):
        im.alpha_composite(A.key(56, 38, "black"), (x - 34, 45 - 6 + 6))
        ImageDraw.Draw(im).text((x - 6, 70), k, font=A.F(26), fill=A.INK + (255,), anchor="mm")
    A.well(im, 880, 44, 1180, 88, 6)
    live(im, 1030, 66, program, 30, A.AMBER)


def key_with_caption(im, cx, cy, cap, kind="black", w=84, h=40, cap_below=False, size=14):
    im.alpha_composite(A.key(w, h, kind), (cx - w // 2 - 6, cy - h // 2 - 6))
    A.caption(im, cx, cy + (h // 2 + 14 if cap_below else -h // 2 - 12), cap, size, width=w + 40)


def page_play():
    im = A.panel(W, H)
    header(im)
    # POWER / VOLUME
    A.section(im, 16, 124, 330, 352, "POWER / VOLUME")
    knob(im, 96, 240, "VOLUME", 0.82)
    knob(im, 250, 240, "OUTPUT %", 1.0)
    key_with_caption(im, 173, 322, "", "black", 110, 34)
    live(im, 173, 322, "PANIC", 20, A.INK)
    # STATUS
    A.section(im, 350, 124, 744, 352, "STATUS")
    A.caption(im, 547, 168, "ENGINE", 15)
    A.well(im, 376, 184, 718, 224)
    live(im, 547, 204, "ready (MIDI ch 1), dropouts 0", 24, A.AMBER)
    A.caption(im, 547, 262, "ORIGINAL VALUE", 15)
    A.well(im, 440, 278, 654, 318)
    live(im, 547, 298, "ORIG VALUE", 24, A.AMBER)
    # keys block
    A.section(im, 764, 124, 1264, 352, "LCD KEYS")
    xs = [822, 946, 1070, 1194]
    for x, c in zip(xs, ("CURSOR <", "CURSOR >", "- / NO", "+ / YES")):
        key_with_caption(im, x, 192, c, "cream", cap_below=False)
    for x, c, kd in ((822, "PAGE -", "cream"), (946, "PAGE +", "cream"), (1194, "WRITE", "red")):
        key_with_caption(im, x, 266, c, kd)
    for x, c in ((822, "EDIT"), (946, "GLOBAL"), (1194, "EXIT")):
        key_with_caption(im, x, 330, c, "cream")
    A.caption(im, 1070, 330, "COMPARE / DEMO", 12, A.INK_DIM)
    # program keys
    A.section(im, 16, 372, 1264, 612, "PROGRAM / EDIT KEYS")
    names = ["COMMON", "VOICE", "PITCH", "OSC 1", "OSC 2", "FILTER", "AMP", "EG", "LFO", "PATCH", "SEQ", "MOD FX", "DELAY FX", "EQ", "ARPEGGIO", "UTILITY"]
    framed = {1, 3, 4, 6, 8, 9, 11, 13, 15, 16}
    for i in range(16):
        cx = 62 + i * 77
        A.caption(im, cx, 428, str(i + 1), 18)
        im.alpha_composite(A.pad(62, 62, (i + 1) in framed, i == 5), (cx - 31 - 8, 480 - 31 - 8))
        A.caption(im, cx, 540, names[i], 13, width=74)
    im.convert("RGB").save(os.path.join(OUT, "play.png"))


def page_filter():
    im = A.panel(W, H)
    header(im)
    A.section(im, 16, 124, 756, 356, "FILTER")
    xs = [96, 240, 384, 528]
    for x, l, p, t in zip(xs, ("CUTOFF", "RESONANCE", "EG1 INT", "KBD TRACK"), ("CUTOFF", "RESONANCE", "FC MOD INT", "E.F.SENSE"), (0.7, 0.3, 0.55, 0.5)):
        knob(im, x, 262, l, t, p)
    key_with_caption(im, 668, 240, "FILTER TYPE", "black", cap_below=False)
    A.pill(im, 668, 186, "FORMANT SHIFT", 11, 120)
    A.well(im, 604, 268, 732, 308)
    live(im, 668, 288, "12LPF", 24, A.AMBER)
    A.section(im, 776, 124, 1264, 356, "AMP")
    for x, l, p, t in ((830, "LEVEL", "LEVEL", 0.8), (935, "PAN", "DIRECT LEVEL", 0.5)):
        knob(im, x, 262, l, t, p)
    for x, cap in ((1063, "EG 2 / GATE"), (1196, "DISTORTION")):
        key_with_caption(im, x, 232, cap, "black", 84, 40)
        A.well(im, x - 56, 268, x + 56, 308)
        live(im, x, 288, "OFF", 24, A.AMBER)
    A.section(im, 16, 376, 632, 612, "EG 1  (FILTER)")
    A.section(im, 648, 376, 1264, 612, "EG 2  (AMP)")
    for row, x0 in ((0, 99), (1, 731)):
        for i, (l, t) in enumerate((("ATTACK", 0.1), ("DECAY", 0.45), ("SUSTAIN", 0.7), ("RELEASE", 0.3))):
            knob(im, x0 + i * 150, 534, l, t, l)
    im.convert("RGB").save(os.path.join(OUT, "filter.png"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    which = sys.argv[1:] or ["play", "filter"]
    if "play" in which: page_play()
    if "filter" in which: page_filter()
    print("done")
