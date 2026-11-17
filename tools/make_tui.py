#!/usr/bin/env python3
"""MS2KR's native MPC skin: skins/TUI.json + skins/Q-Links.json + the PNGs they use (docs/SDK-PORTING.md; the widget machinery is
Vavra's tools/make_tui.py). The art is drawn from code by tools/ms2k_art.py in the look of the MS2000R's panel; the pages are laid
out here, every control in a block of four with its own Q-Link frame (at most four blocks per tab).

The firmware's own LCD (two lines: program, parameter, value) is the only program / value display; the engine status is its small
third line. The 16 program keys are the hardware's key matrix: they pick programs 1-16 of the bank outside EDIT and the edit page in EDIT.
    python3 tools/make_tui.py              # -> skins/   (build-sdk.sh copies it to Plugin Skins/)
    python3 tools/make_tui.py --preview    # also docs/skin-preview/<tab>.png, composed offline (Titillium at the MPC's text scale)"""
import json, math, os, re, shutil, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms2k_art as A

ROOT = A.ROOT
OUT = os.environ.get("MS2KR_SKIN_OUT", os.path.join(ROOT, "skins"))
PREVIEW = os.environ.get("MS2KR_PREVIEW", os.path.join(ROOT, "docs", "skin-preview"))
LOCK = [l.strip() for l in open(os.path.join(ROOT, "params.lock")) if l.strip()]
TUI_PX = 0.64                                        # a Label draws its text at about this fraction of its height
GESTURE = "Instant"
KNOB = 84
CLEAR = "clear.png"
FAV_MAX = int(re.search(r"kFavNameMax = (\d+)", open(os.path.join(ROOT, "src", "params_gen.h")).read()).group(1))


def PI(key):
    return LOCK.index(key)


def P(key):
    return "Parameter %d" % PI(key)


def hexcol(rgb, a=255):
    return "%02x%02x%02x%02x" % ((a,) + tuple(rgb))


# ---- a JSON writer that keeps key order and allows the overlay widgets' duplicate "version" key ------------------------------
class Obj:
    def __init__(self, *pairs):
        self.pairs = list(pairs)


def dump(v, ind=0):
    sp = "  " * ind
    pairs = v.pairs if hasattr(v, "pairs") else list(v.items()) if isinstance(v, dict) else None
    if pairs is not None:
        if not pairs:
            return "{}"
        return "{\n%s\n%s}" % (",\n".join("%s  %s: %s" % (sp, dump(k), dump(x, ind + 1)) for k, x in pairs), sp)
    if isinstance(v, list):
        return "[]" if not v else "[\n%s\n%s]" % (",\n".join(sp + "  " + dump(x, ind + 1) for x in v), sp)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
    return '"%s"' % str(v).replace("\\", "\\\\").replace('"', '\\"')


# ---- TUI building blocks --------------------------------------------------------------------------------------------------
def bounds(b, focus="No", ind=None):
    d = {"version": 2 if ind else 1, "acceptsHWFocus": focus, "showWhenDataModelInvalid": "Show", "whenVisible": "Always",
         "boundsType": "Absolute", "bounds": b}
    if ind:
        d["additionalInvalidatingHandles"] = ind
    return d


def entry(name, typ, data, b, remap=None, focus="No", ind=None, visible=None):
    e = {"version": 2, "componentData": {"version": 1, "name": name, "type": typ, "data": data},
         "handle remapping": {"version": 1, "map": [{"key": "Data", "value": remap}] if remap else []},
         "bounds": bounds(b, focus, ind)}
    if visible:
        e["bounds"]["whenVisible"] = visible
    return e


def bg(colour="0", image=""):
    return {"version": 1, "focussed": {"version": 1, "colour": colour, "image": image}, "unfocussed": {"version": 1, "colour": colour, "image": image}}


def component(children, actions=None, ignore=False, background=None):
    return {"version": 2, "actions": actions or [], "backgroundData": background or bg(), "ignoreMousePresses": ignore,
            "disableCoarseDataWheel": False, "componentsData": children}


def act(on, handler, extra=""):
    return {"version": 1, "onAction": on, "handler": handler, "handleName": "Data", "additionalData": extra}


def text_style(h, colour, just="horizontallyCentred verticallyCentred", style="SemiBold"):
    return {"version": 1, "font": {"version": 1, "name": "Titillium Web", "style": style, "height": float(h)}, "colour": colour,
            "justification": just, "case": "Original"}


def label(b, key, h=22, colour=None, just="horizontallyCentred verticallyCentred", style="SemiBold"):
    colour = colour or hexcol(A.INK)
    return entry("label", "Label", {"version": 1, "textStyle": text_style(h, colour, just, style), "type": "Value", "handleName": "Data"}, b, P(key))


def focus_style():
    return {"version": 1, "backgroundColour": "00000000", "outlineColour": hexcol((255, 210, 120)), "backgroundInset": 4.0, "outlineThickness": 2.0}


FIELDS = set()


def definitions():
    knob = component([
        entry("focus", "Focus", focus_style(), "-4 -4 %d %d" % (KNOB + 8, KNOB + 8), visible="WhenFocussed"),
        entry("knob", "Knob", {"version": 3, "knobType": "FilmStrip", "filmStrip": "msknob.png", "numFrames": 101, "invert": False,
                               "dragOrientation": "Vertical", "handleName": "Data"}, "0 0 %d %d" % (KNOB, KNOB)),
    ], actions=[act("Mouse Down", "Q-Link"), act("Double Click", "Show Overlay", "knob overlay"), act("Enter Pressed", "Show Overlay", "knob overlay")])
    overlay = component([entry("overlay", "KnobOverlay", Obj(
        ("version", 2), ("version", 1),
        ("actions", [{"version": 1, "onAction": "Focus Lost", "handler": "Focus Lost", "handleName": "Focus Lost", "additionalData": ""}]),
        ("overlayType", "Knob With Header"), ("scaleType", "Linear"), ("polarityType", "Unipolar"),
        ("showMinusSign", True), ("handleName", "Data")), "0 0 1280 800", focus="Yes")], ignore=True)
    out = [{"key": "knob overlay", "value": overlay}, {"key": "msknob", "value": knob}]
    for w, h in sorted(FIELDS):      # an invisible value slider over a live name: the data wheel, a Q-Link or a drag steps it
        ts = {"version": 1, "font": {"version": 1, "name": "Roboto", "style": "Regular", "height": 20.0}, "colour": "00000000",
              "justification": "horizontallyCentred verticallyCentred", "case": "Original"}
        out.append({"key": "lcdfield%dx%d" % (w, h), "value": component([
            entry("focus", "Focus", focus_style(), "0 0 %d %d" % (w, h), visible="WhenFocussed"),
            entry("field", "Knob", {"version": 4, "knobType": "ValueSlider", "textStyle": ts, "dragOrientation": "Horizontal",
                                    "handleName": "Data"}, "0 0 %d %d" % (w, h)),
        ], actions=[act("Mouse Down", "Q-Link")])})
    return out


def save(im, name):
    im.save(os.path.join(OUT, name))
    return name


def button(kids, key, b, on, off, bid=1, n=1, name=None):
    kids.append(entry(name or key, "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": bid, "numButtonsInGroup": n,
                                              "handleName": "Data", "gestureBehaviour": GESTURE}, b, remap=P(key)))


# ---- a page: art + widgets at the same coordinates + Q-Link blocks -----------------------------------------------------------
PILLS = {}
HDR_Y = 112          # the header (wordmark, LCD, program keys) ends here


class Page:
    def __init__(self, name, fn, random=False, keyboard=False):
        self.name, self.fn = name, fn
        self.art = A.panel()
        self.kids, self.overlay = [], []
        self.pos = {}                 # key -> (x0, y0, x1, y1) of the control with its caption
        self.blocks = []              # [(keys, rect)]
        self.header(random)
        self.keyboard = keyboard

    # the header: wordmark, the one LCD, PROG - / + , RANDOM, the ORIGINAL VALUE lamp
    def header(self, random):
        A.wordmark(self.art, 26, 12)
        A.lcd(self.art, 330, 8, 880, 108)
        k = self.kids
        k.append(label("346 12 520 44", "lcd1", 40, hexcol(A.LCD_INK), "left verticallyCentred", "Bold"))
        k.append(label("346 54 520 44", "lcd2", 40, hexcol(A.LCD_INK), "left verticallyCentred", "Bold"))
        k.append(label("560 88 312 18", "status", 18, hexcol((70, 92, 20)), "right verticallyCentred", "SemiBold"))
        FIELDS.add((550, 100))
        k.append(entry("program field", "lcdfield550x100", {"version": 1, "handleName": "Data"}, "330 8 550 100", remap=P("program"), focus="Yes"))
        self.pos["program"] = (330, 8, 880, 108)
        for x, key, g in ((938, "prog_prev", "-"), (1022, "prog_next", "+")):
            self.button_img(key, x, 36, 64, 40, "black", g, 30)
        A.caption(self.art, 980, 82, "PROGRAM", 14)
        if random:
            self.button_img("random_patch", 1128, 36, 110, 40, "black", "RANDOM", 17, ink=A.AMBER)
        A.caption(self.art, 1210, 74, "ORIGINAL VALUE", 12, A.INK_DIM)
        A.well(self.art, 1166, 84, 1254, 106, 5)
        k.append(label("1166 84 88 22", "led_orig", 15, hexcol(A.AMBER)))

    def button_img(self, key, cx, cy, w, h, kind, text=None, size=20, ink=None):
        slug = re.sub(r"[^a-z0-9]+", "_", (text or "x").lower().replace("+", "plus").replace("-", "minus")).strip("_")
        nm = "key_%s_%dx%d_%s" % (kind, w, h, slug)
        on = save(A.glyph_key(w, h, kind, True, text, size, ink), nm + "_on.png")
        off = save(A.glyph_key(w, h, kind, False, text, size, ink), nm + "_off.png")
        button(self.kids, key, "%d %d %d %d" % (cx - (w + 12) // 2, cy - (h + 12) // 2, w + 12, h + 12), on, off)

    # controls
    def knob(self, key, cx, gc, cap, pill=None, exact=False):
        """gc = the vertical centre of the section's content: the knob with its caption above and its scale round it is centred on it"""
        cy = gc if exact else gc + 15
        A.ticks(self.art, cx, cy, 46)
        A.caption(self.art, cx, cy - 74, cap, 15, width=140)
        if pill:
            A.pill(self.art, cx, cy - 56, pill, 11, 130)
        self.kids.append(entry(key, "msknob", {"version": 1, "handleName": "Data"}, "%d %d %d %d" % (cx - KNOB // 2, cy - KNOB // 2, KNOB, KNOB),
                               remap=P(key), focus="Yes"))
        self.pos[key] = (cx - 62, cy - 86, cx + 62, cy + 56)

    def key(self, key, cx, gc, cap, kind="black", w=92, h=42, led=None, pill=None, space=False, exact=False):
        """a panel key with its caption above (and an optional boxed second caption above that), its LED readout in a well below. gc = the
        vertical centre of the section's content: the group (caption .. well) is centred on it; space keeps the room of a readout that is not there"""
        top = h // 2 + (45 if pill else 25)
        bot = h // 2 + (50 if (led or space) else 8)
        cy = gc if exact else int(round(gc - (bot - top) / 2.0))
        nm = "key_%s_%dx%d" % (kind, w, h)
        if not os.path.exists(os.path.join(OUT, nm + "_off.png")):
            save(A.key(w, h, kind, False), nm + "_off.png")
            save(A.key(w, h, kind, True), nm + "_on.png")
        A.caption(self.art, cx, cy - h // 2 - 13, cap, 14, width=w + 50)
        if pill:
            A.pill(self.art, cx, cy - h // 2 - 33, pill, 11, w + 50)
        button(self.kids, key, "%d %d %d %d" % (cx - (w + 12) // 2, cy - (h + 12) // 2, w + 12, h + 12), nm + "_on.png", nm + "_off.png")
        if led:
            self.readout(led, cx, cy + h // 2 + 32, max(w + 20, 110))

    def readout(self, key, cx, cy, w=120, h=34, size=22):
        A.well(self.art, cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2, 6)
        self.kids.append(label("%d %d %d %d" % (cx - w // 2 + 4, cy - h // 2, w - 8, h), key, size, hexcol(A.AMBER), style="Bold"))

    # Q-Link blocks
    def block(self, keys, rect=None, pad=4):
        ks = [k for k in keys if k]
        if rect is None:
            boxes = [self.pos[k] for k in ks]
            rect = (min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad, max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)
        assert len(self.blocks) < 4, "%s: more than four Q-Link blocks" % self.name
        self.blocks.append((ks, rect))

    def section(self, x0, y0, x1, y1, title):
        A.section(self.art, x0, y0, x1, y1, title)

    def tab(self, bgfile):
        kids = [entry("bg", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": bgfile}, "0 0 1280 628")] + self.kids + self.overlay
        groups = ["%d %d %d %d" % (r[0], r[1], r[2] - r[0], r[3] - r[1]) for _, r in self.blocks]
        return {"version": 1, "tabName": self.name, "fnKeyIndex": self.fn, "fnKeySubIndex": 0,
                "componentDefinition": component(kids, background=bg(hexcol(A.TEAL))), "qlinkBoundsData": groups}


def spread(x0, x1, n):
    """n evenly spaced centres across [x0, x1]: the same margin at both ends"""
    w = (x1 - x0) / n
    return [int(round(x0 + w * (i + 0.5))) for i in range(n)]


# ---- the pages ---------------------------------------------------------------------------------------------------------------
def page_play(fn):
    pg = Page("PLAY", fn, random=True)
    pg.section(16, 128, 420, 372, "POWER / VOLUME")
    for x, k, c in zip(spread(16, 420, 2), ("vol", "out_level"), ("VOLUME", "OUTPUT %")):
        pg.knob(k, x, 238, c, exact=True)
    pg.button_img("panic", 218, 338, 130, 36, "black", "PANIC", 18)
    pg.section(440, 128, 1264, 372, "LCD KEYS")
    xs = spread(440, 1264, 4)
    rows = (204, 272, 340)
    for x, k, c in zip(xs, ("k_curl", "k_curr", "k_no", "k_yes"), ("CURSOR <", "CURSOR >", "- / NO", "+ / YES")):
        pg.key(k, x, rows[0], c, "cream", 100, 40, exact=True)
    for x, k, c, kd in ((xs[0], "k_pagem", "PAGE -", "cream"), (xs[1], "k_pagep", "PAGE +", "cream"), (xs[3], "k_write", "WRITE", "red")):
        pg.key(k, x, rows[1], c, kd, 100, 40, exact=True)
    for x, k, c in ((xs[0], "k_edit", "EDIT"), (xs[1], "k_global", "GLOBAL"), (xs[3], "k_exit", "EXIT")):
        pg.key(k, x, rows[2], c, "cream", 100, 40, exact=True)
    pg.section(16, 388, 1264, 614, "PROGRAM / EDIT KEYS")
    names = ["COMMON", "VOICE", "PITCH", "OSC 1", "OSC 2", "FILTER", "AMP", "EG", "LFO", "PATCH", "SEQ", "MOD FX", "DELAY FX", "EQ", "ARPEGGIO", "UTILITY"]
    framed = {1, 3, 4, 6, 8, 9, 11, 13, 15, 16}
    for i, cx in enumerate(spread(36, 1244, 16)):
        A.caption(pg.art, cx, 438, str(i + 1), 18)
        A.caption(pg.art, cx, 562, names[i], 13, width=76)
        on = save(A.pad(62, 62, (i + 1) in framed, True), "pad%d_on.png" % (i + 1))
        off = save(A.pad(62, 62, (i + 1) in framed, False), "pad%d_off.png" % (i + 1))
        button(pg.kids, "k_pad%d" % (i + 1), "%d %d 78 78" % (cx - 39, 500 - 39), on, off)
    pg.block(["vol", "out_level"])
    pg.block(["program"], rect=(330, 8, 880, 108))
    return pg


def page_banks(fn):
    pg = Page("BANKS", fn, random=True)
    # the bank tiles (A-H), the 16 programs of the bank (2 x 8, down the columns), the favourite keys
    pg.section(16, 128, 270, 614, "BANKS")
    tiles = []

    def tile(key, x, y, w, h, size=22):
        pg.art.alpha_composite(A.tile(w, h, False), (x - 4, y - 4))
        pg.kids.append(label("%d %d %d %d" % (x + 30, y, w - 36, h), key, size, hexcol(A.INK), "left verticallyCentred"))
        nm = "tile_on_%dx%d.png" % (w, h)
        if not os.path.exists(os.path.join(OUT, nm)):
            save(A.tile(w, h, True), nm)
        button(pg.kids, key, "%d %d %d %d" % (x - 4, y - 4, w + 8, h + 8), nm, CLEAR, name=key + " tile")

    for i in range(8):
        tile("bank_slot_%d" % (i + 1), 32, 164 + i * 56, 222, 46)
    pg.section(290, 128, 1000, 614, "PROGRAMS OF THE BANK")
    for c in range(2):
        for r in range(8):
            tile("patch_slot_%d" % (c * 8 + r + 1), 308 + c * 346, 164 + r * 56, 336, 46)
    pg.section(1020, 128, 1264, 614, "FAVOURITES")
    for k, c, y in (("fav_save", "+ FAV", 296), ("fav_delete", "- FAV", 446)):
        pg.button_img(k, 1142, y, 150, 54, "black", c, 22)
    pg.block(["program"], rect=(330, 8, 880, 108))
    pg.keyboard = True
    return pg


def page_osc(fn):
    pg = Page("OSC", fn)
    pg.section(16, 128, 628, 392, "OSCILLATOR 1")
    xs = spread(16, 628, 3)
    pg.key("k_o1wave", xs[0], 260, "WAVE", w=96, led="led_o1wave", pill="WAVE")
    pg.knob("o1c1", xs[1], 260, "CONTROL 1", "CONTROL 1")
    pg.knob("o1c2", xs[2], 260, "CONTROL 2", "CONTROL 2")
    pg.section(644, 128, 1264, 392, "OSCILLATOR 2")
    xs = spread(644, 1264, 4)
    pg.key("k_o2wave", xs[0], 260, "WAVE", w=96, led="led_o2wave")
    pg.key("k_o2mod", xs[1], 260, "OSC MOD", w=96, led="led_o2mod")
    pg.knob("o2semi", xs[2], 260, "SEMITONE", "HPF LEVEL")
    pg.knob("o2tune", xs[3], 260, "TUNE", "THRESHOLD")
    pg.section(16, 408, 600, 614, "MIXER")
    xs = spread(16, 600, 3)
    for x, k, c, p in zip(xs, ("mx1", "mx2", "mxn"), ("OSC 1", "OSC 2", "NOISE"), ("OSC 1", "INST", "NOISE")):
        pg.knob(k, x, 511, c, p)
    pg.section(616, 408, 940, 614, "PORTAMENTO")
    pg.knob("porta", 778, 511, "TIME", "TIME")
    pg.section(956, 408, 1264, 614, "TIMBRE SELECT")
    pg.key("k_timbre", 1110, 511, "SELECT", "cream", 100, 40, led="led_timbre")
    pg.block(["o1c1", "o1c2"])
    pg.block(["o2semi", "o2tune"])
    pg.block(["mx1", "mx2", "mxn"])
    pg.block(["porta"])
    return pg


def page_filter(fn):
    pg = Page("FILTER / EG", fn)
    pg.section(16, 128, 756, 372, "FILTER")
    xs = spread(16, 756, 5)
    for x, k, c, p in zip(xs, ("cut", "res", "eg1int", "kbdtr"), ("CUTOFF", "RESONANCE", "EG1 INT", "KBD TRACK"), ("CUTOFF", "RESONANCE", "FC MOD INT", "E.F.SENSE")):
        pg.knob(k, x, 250, c, p)
    pg.key("k_ftype", xs[4], 250, "FILTER TYPE", w=96, led="led_ftype", pill="FORMANT SHIFT")
    pg.section(776, 128, 1264, 372, "AMP")
    xs = spread(776, 1264, 4)
    pg.knob("lvl", xs[0], 250, "LEVEL", "LEVEL")
    pg.knob("pan", xs[1], 250, "PAN", "DIRECT LEVEL")
    pg.key("k_eg2gate", xs[2], 250, "EG 2 / GATE", w=96, led="led_eg2gate")
    pg.key("k_dist", xs[3], 250, "DISTORTION", w=96, led="led_dist", pill="DISTORTION")
    for x0, x1, title, ks in ((16, 632, "EG 1  (FILTER)", ("eg1a", "eg1d", "eg1s", "eg1r")), (648, 1264, "EG 2  (AMP)", ("eg2a", "eg2d", "eg2s", "eg2r"))):
        pg.section(x0, 388, x1, 614, title)
        for x, k, c in zip(spread(x0, x1, 4), ks, ("ATTACK", "DECAY", "SUSTAIN", "RELEASE")):
            pg.knob(k, x, 501, c, c)
    pg.block(["cut", "res", "eg1int", "kbdtr"])
    pg.block(["lvl", "pan"])
    pg.block(["eg1a", "eg1d", "eg1s", "eg1r"])
    pg.block(["eg2a", "eg2d", "eg2s", "eg2r"])
    return pg


def page_lfo(fn):
    pg = Page("LFO / FX / PATCH", fn)
    pg.section(16, 128, 400, 392, "LFO 1")
    xs = spread(16, 400, 2)
    pg.key("k_lfo1", xs[0], 260, "SELECT", w=96, led="led_lfo1", pill="SELECT")
    pg.knob("lfo1f", xs[1], 260, "FREQUENCY", "FREQUENCY")
    pg.section(416, 128, 800, 392, "LFO 2")
    xs = spread(416, 800, 2)
    pg.key("k_lfo2", xs[0], 260, "SELECT", w=96, led="led_lfo2", pill="SELECT")
    pg.knob("lfo2f", xs[1], 260, "FREQUENCY", "FREQUENCY")
    pg.section(816, 128, 1264, 392, "MOD / DELAY EFFECT")
    xs = spread(816, 1264, 3)
    pg.key("k_fxsel", xs[0], 260, "MOD / DELAY", w=96, led="led_fx", pill="MOD / DELAY")
    pg.knob("fxspd", xs[1], 260, "SPEED / TIME", "SPEED / TIME")
    pg.knob("fxdep", xs[2], 260, "DEPTH / FEEDBACK", "DEPTH / FB")
    pg.section(16, 408, 1264, 614, "VIRTUAL PATCH")
    kx = spread(16, 640, 3)
    pg.key("k_vpsel", kx[0], 511, "SELECT", w=96, led="led_vpsel")
    pg.key("k_vpsrc", kx[1], 511, "SOURCE", w=96, led="led_vpsrc", pill="FC MOD SOURCE")
    pg.key("k_vpdst", kx[2], 511, "DESTINATION", w=96, led="led_vpdst")
    for x, k, c in zip(spread(640, 1264, 4), ("patch1", "patch2", "patch3", "patch4"), ("PATCH 1", "PATCH 2", "PATCH 3", "PATCH 4")):
        pg.knob(k, x, 501, c)
    pg.block(["lfo1f"])
    pg.block(["lfo2f"])
    pg.block(["fxspd", "fxdep"])
    pg.block(["patch1", "patch2", "patch3", "patch4"])
    return pg


def page_arp(fn):
    pg = Page("ARP / SEQ", fn)
    pg.section(16, 128, 860, 392, "ARPEGGIATOR")
    xs = spread(30, 848, 6)
    pg.knob("tempo", xs[0], 260, "TEMPO")
    pg.knob("gate", xs[1], 260, "GATE")
    for x, k, c, l in zip(xs[2:], ("k_arpon", "k_arplat", "k_arprng", "k_arptyp"), ("ON / OFF", "LATCH", "RANGE", "TYPE"), ("led_arp", "led_latch", None, None)):
        pg.key(k, x, 260, c, w=92, led=l, space=True)
    pg.section(876, 128, 1264, 392, "MOD SEQUENCE")
    xs = spread(876, 1264, 2)
    pg.key("k_mseqon", xs[0], 260, "ON / OFF", w=92, led="led_mseq")
    pg.key("k_mseqrec", xs[1], 260, "REC", "cream", 92, 40, led="led_mrec")
    pg.section(16, 408, 400, 614, "KEYBOARD")
    pg.key("k_kbd", 208, 511, "KEYBOARD", "cream", 100, 40, led="led_kbd")
    pg.section(416, 408, 800, 614, "BANK / OCTAVE")
    xs = spread(416, 800, 2)
    pg.key("k_bankdn", xs[0], 511, "DOWN", "cream", 100, 40)
    pg.key("k_bankup", xs[1], 511, "UP", "cream", 100, 40)
    pg.section(816, 408, 1264, 614, "SEQ EDIT")
    pg.key("k_seqsel", 1040, 511, "SELECT", "cream", 100, 40, led="led_seq")
    pg.block(["tempo", "gate"])
    return pg


PAGES = [page_play, page_banks, page_osc, page_filter, page_lfo, page_arp]


# ---- the naming keyboard for +FAV (Profit-5's) ------------------------------------------------------------------------------
KB_ROWS = [("1234567890", ["kb_bksp"]), ("QWERTYUIOP", []), ("ASDFGHJKL-", []), ("ZXCVBNM", ["kb_space"])]


def keyboard(pg):
    """a full-page panel over the BANKS page, shown while kb_open = 1 (added last, so it is on top)"""
    ind = ["IndexedEnabling/1/2/Parameter %d" % PI("kb_open")]
    panel = A.panel()
    d = ImageDraw.Draw(panel)
    A.section(panel, 20, 20, 1260, 610, "FAVOURITE NAME")
    A.lcd(panel, 64, 48, 900, 112)
    A.caption(panel, 1080, 80, "MAX %d CHARACTERS" % FAV_MAX, 17, A.INK_DIM, width=300)
    pg.overlay.append(entry("kb panel", "Image", {"version": 2, "imageType": "Regular", "colour": "0", "image": save(panel.convert("RGB"), "kb_panel.png")},
                            "0 0 1280 628", ind=ind))
    pg.overlay.append(entry("kb name", "Label", {"version": 1, "textStyle": text_style(48, hexcol(A.LCD_INK), "left verticallyCentred", "Bold"),
                                                 "type": "Value", "handleName": "Data"}, "80 48 800 64", P("fav_name"), ind=ind))
    kw, kh, gap, x0, y0 = 98, 74, 8, 64, 140

    def kbkey(k, cap, x, y, w):
        nm = "kb_%s_%d" % (re.sub(r"[^a-z0-9]", "", k.lower()), w)
        on = save(A.glyph_key(w, kh, "black", True, cap, 30 if len(cap) == 1 else 22), nm + "_on.png")
        off = save(A.glyph_key(w, kh, "black", False, cap, 30 if len(cap) == 1 else 22), nm + "_off.png")
        pg.overlay.append(entry(k, "Button", {"version": 2, "onImage": on, "offImage": off, "buttonId": 1, "numButtonsInGroup": 1,
                                              "handleName": "Data", "gestureBehaviour": GESTURE},
                                "%d %d %d %d" % (x - 6, y - 6, w + 12, kh + 12), remap=P(k), ind=ind))
    for r, (chars, extra) in enumerate(KB_ROWS):
        y = y0 + r * (kh + gap)
        x = x0 + r * 30
        for c in chars:
            kbkey("kb_" + ("dash" if c == "-" else c.lower()), c, x, y, kw)
            x += kw + gap
        for k in extra:
            kbkey(k, {"kb_bksp": "DELETE", "kb_space": "SPACE"}[k], x, y, 1216 - x)
    y = y0 + 4 * (kh + gap)
    kbkey("kb_shift", "SHIFT", x0, y, 220)
    kbkey("kb_cancel", "CANCEL", 640 - 130, y, 260)
    kbkey("kb_save", "SAVE", 1216 - 260, y, 260)


# ---- Q-Links, preview, main ---------------------------------------------------------------------------------------------------
def qlinks_for(pages):
    maps = []
    for pg in pages:
        q = {"Q-Link %d" % n: -1 for n in range(1, 17)}
        column = bool(pg.blocks) and all((r[3] - r[1]) > (r[2] - r[0]) for _, r in pg.blocks)
        for gi, (keys, _) in enumerate(pg.blocks[:4]):
            for i, key in enumerate(keys[:4]):
                q["Q-Link %d" % ((13 + gi - 4 * i) if column else (13 - 4 * gi + i))] = PI(key)
        maps.append({"Tab": pg.fn + 1, "SubTab": 1, "Bank Direction": "Column" if column else "RowTopDown", "Q-Links": q})
    return {"version": 4, "info": {"version": 1, "type": "CompleteDescription"},
            "Screen Mode Q-Links": {"version": 4, "map": maps}, "Program Mode Q-Links": {"Q-Link %d" % n: -1 for n in range(1, 17)}}


SAMPLE = {"lcd1": "B03:Silk Pad", "lcd2": "Single     =120", "status": "ready (MIDI ch 1), dropouts 0", "led_orig": "",
          "led_o1wave": "SAW", "led_o2wave": "SAW", "led_o2mod": "OFF", "led_ftype": "12LPF", "led_timbre": "1", "led_seq": "SEQ 1",
          "led_lfo1": "SAW", "led_lfo2": "SAW", "led_vpsel": "PATCH 1", "led_vpsrc": "LFO 1", "led_vpdst": "PITCH", "led_eg2gate": "EG 2",
          "led_dist": "OFF", "led_fx": "MOD", "led_mseq": "OFF", "led_mrec": "OFF", "led_arp": "OFF", "led_latch": "OFF", "led_kbd": "OFF",
          "fav_name": "My Pad_"}
PROGS = ["Stab Saw", "Soft Keys", "Silk Pad", "Mono Lead", "Dirty Sync", "Zoop Mania", "Ice Field", "Bell Wave"]


def sample_text(key):
    if key in SAMPLE:
        return SAMPLE[key]
    if key.startswith("bank_slot_"):
        return "BANK " + "ABCDEFGH"[int(key[10:]) - 1]
    if key.startswith("patch_slot_"):
        i = int(key[11:])
        return "B%02d %s" % (i, PROGS[i % len(PROGS)])
    return ""


def preview(pages, arts, defs, keyboard=False):
    os.makedirs(PREVIEW, exist_ok=True)
    kb = "IndexedEnabling/1/2/Parameter %d" % PI("kb_open")
    strip = Image.open(os.path.join(OUT, "msknob.png"))
    for pg in pages:
        im = Image.open(os.path.join(OUT, arts[pg.name])).convert("RGBA")
        d = ImageDraw.Draw(im)
        if keyboard and not pg.keyboard:
            continue
        for e in pg.kids + (pg.overlay if keyboard else []):
            cd = e["componentData"]
            x, y, w, h = [int(float(v)) for v in e["bounds"]["bounds"].split()]
            hs = e["bounds"].get("additionalInvalidatingHandles", [])
            if (kb in hs) != keyboard and not (not keyboard and kb not in hs):
                continue
            if cd["type"] == "msknob":
                f = 60
                im.alpha_composite(strip.crop((0, KNOB * f, KNOB, KNOB * (f + 1))).convert("RGBA"), (x, y))
            elif cd["type"] == "Image" and keyboard:
                im.alpha_composite(Image.open(os.path.join(OUT, cd["data"]["image"])).convert("RGBA"), (x, y))
            elif cd["type"] == "Label":
                key = LOCK[int(e["handle remapping"]["map"][0]["value"].split()[1])]
                ts = cd["data"]["textStyle"]
                cen = "horizontallyCentred" in ts["justification"]
                right = ts["justification"].startswith("right")
                col = tuple(int(ts["colour"][i:i + 2], 16) for i in (2, 4, 6))
                f = A.F(max(8, int(ts["font"]["height"] * TUI_PX)), ts["font"]["style"] == "Bold")
                s = sample_text(key)
                d.text((x + w / 2 if cen else x + w - 2 if right else x + 2, y + h / 2), s, font=f, fill=col, anchor="mm" if cen else "rm" if right else "lm")
            elif cd["type"] == "Button" and cd["data"]["offImage"] != CLEAR:
                im.alpha_composite(Image.open(os.path.join(OUT, cd["data"]["offImage"])).convert("RGBA"), (x, y))
            elif cd["type"] == "Button" and cd["name"] in ("bank_slot_1 tile", "patch_slot_1 tile"):
                im.alpha_composite(Image.open(os.path.join(OUT, cd["data"]["onImage"])).convert("RGBA"), (x, y))
        if not keyboard:
            for _, r in pg.blocks:
                d.rectangle(r, outline=(255, 255, 255, 200), width=2)
        name = re.sub(r"[^a-z0-9]+", "_", pg.name.lower()).strip("_")
        im.convert("RGB").save(os.path.join(PREVIEW, "%s%s.png" % (name, "_keyboard" if keyboard else "")))


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    save(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), CLEAR)
    save(A.knob_strip(KNOB, 101), "msknob.png")
    pages, arts, tabs = [], {}, []
    for fn, make in enumerate(PAGES):
        pg = make(fn)
        if pg.keyboard:
            keyboard(pg)
        arts[pg.name] = save(pg.art.convert("RGB"), "bg_%s.png" % re.sub(r"[^a-z0-9]+", "_", pg.name.lower()).strip("_"))
        pages.append(pg)
        tabs.append(pg.tab(arts[pg.name]))
    for pg in pages:   # the Q-Link frames of one tab must not overlap (the MPC draws them all)
        rs = [r for _, r in pg.blocks]
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), "%s: Q-Link frames overlap %s %s" % (pg.name, a, b)
    on_q = {k for pg in pages for _, (keys) in [(0, k) for k, _ in pg.blocks] for k in keys}
    shown = {k for pg in pages for k in pg.pos}
    missing = sorted(shown - on_q)
    if missing:
        print("controls on no Q-Link:", ", ".join(missing))
    defs = definitions()
    tui = {"pageData": {"version": 1, "componentDefinitions": {"version": 2, "importFiles": [], "localComponentDefinitions": defs},
                        "replacementStrings": [], "info": {"version": 1, "type": "CompleteDescription"}, "tabs": tabs}}
    open(os.path.join(OUT, "TUI.json"), "w").write(dump(tui) + "\n")
    open(os.path.join(OUT, "Q-Links.json"), "w").write(dump(qlinks_for(pages)) + "\n")
    bad = [f for f in os.listdir(OUT) if re.search(r'[<>:"/\\|?*]', f)]
    assert not bad, "file names that exFAT rejects: %s" % bad
    low = [f.lower() for f in os.listdir(OUT)]
    assert len(low) == len(set(low)), "file names that differ only in case"
    assert "object at" not in open(os.path.join(OUT, "TUI.json")).read()
    if "--preview" in sys.argv:
        preview(pages, arts, {x["key"]: x["value"] for x in defs})
        preview(pages, arts, {x["key"]: x["value"] for x in defs}, keyboard=True)
    print("wrote", OUT, "-", len(tabs), "tabs,", len(os.listdir(OUT)), "files")


if __name__ == "__main__":
    main()
