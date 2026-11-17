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


def header(im, status="ready (MIDI ch 1), dropouts 0", random=True):
    """wordmark, ONE main LCD (the firmware's own two lines: program, parameter, value) with the engine status as its small third line,
    PROG - / + and RANDOM beside it, the ORIGINAL VALUE lamp under them"""
    A.wordmark(im, 26, 12)
    A.lcd(im, 330, 8, 880, 108)
    live(im, 348, 36, "B03:Silk Pad", 36, A.LCD_INK, anchor="lm")
    live(im, 348, 72, "Single     =120", 36, A.LCD_INK, anchor="lm")
    live(im, 866, 94, status, 15, A.LCD_LO if False else (84, 104, 24), bold=False, anchor="rm")
    for x, k in ((938, "-"), (1022, "+")):
        im.alpha_composite(A.key(64, 40, "black"), (x - 38, 16))
        ImageDraw.Draw(im).text((x - 6, 32), k, font=A.F(28), fill=A.INK + (255,), anchor="mm")
    A.caption(im, 980, 76, "PROGRAM", 14)
    if random:
        im.alpha_composite(A.key(110, 40, "black"), (1128 - 61, 16))
        ImageDraw.Draw(im).text((1128, 32), "RANDOM", font=A.F(17), fill=A.AMBER + (255,), anchor="mm")
    A.caption(im, 1210, 76, "ORIGINAL VALUE", 12, A.INK_DIM)
    ImageDraw.Draw(im).ellipse((1204, 90, 1216, 102), fill=(60, 16, 12, 255), outline=(150, 170, 180, 200))


def key_with_caption(im, cx, cy, cap, kind="black", w=84, h=40, cap_below=False, size=14):
    im.alpha_composite(A.key(w, h, kind), (cx - w // 2 - 6, cy - h // 2 - 6))
    A.caption(im, cx, cy + (h // 2 + 14 if cap_below else -h // 2 - 12), cap, size, width=w + 40)


def page_play():
    im = A.panel(W, H)
    header(im)
    # POWER / VOLUME
    A.section(im, 16, 134, 420, 364, "POWER / VOLUME")
    knob(im, 120, 250, "VOLUME", 0.82)
    knob(im, 316, 250, "OUTPUT %", 1.0)
    key_with_caption(im, 218, 330, "", "black", 120, 34)
    live(im, 218, 330, "PANIC", 20, A.INK)
    # keys block (the hardware's LCD keys)
    A.section(im, 440, 134, 1264, 364, "LCD KEYS")
    xs = [520, 690, 860, 1030]
    for x, c in zip(xs, ("CURSOR <", "CURSOR >", "- / NO", "+ / YES")):
        key_with_caption(im, x, 204, c, "cream", 96, 42)
    for x, c, kd in ((520, "PAGE -", "cream"), (690, "PAGE +", "cream"), (1180, "WRITE", "red")):
        key_with_caption(im, x, 276, c, kd, 96, 42)
    for x, c in ((520, "EDIT"), (690, "GLOBAL"), (1180, "EXIT")):
        key_with_caption(im, x, 340, c, "cream", 96, 36)
    A.caption(im, 860, 340, "COMPARE / DEMO", 12, A.INK_DIM)
    # program keys
    A.section(im, 16, 380, 1264, 612, "PROGRAM / EDIT KEYS")
    names = ["COMMON", "VOICE", "PITCH", "OSC 1", "OSC 2", "FILTER", "AMP", "EG", "LFO", "PATCH", "SEQ", "MOD FX", "DELAY FX", "EQ", "ARPEGGIO", "UTILITY"]
    framed = {1, 3, 4, 6, 8, 9, 11, 13, 15, 16}
    for i in range(16):
        cx = 62 + i * 77
        A.caption(im, cx, 428, str(i + 1), 18)
        im.alpha_composite(A.pad(62, 62, (i + 1) in framed, False), (cx - 31 - 8, 480 - 31 - 8))
        A.caption(im, cx, 540, names[i], 13, width=74)
    im.convert("RGB").save(os.path.join(OUT, "play.png"))


def page_filter():
    im = A.panel(W, H)
    header(im, random=False)
    A.section(im, 16, 134, 756, 356, "FILTER")
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
