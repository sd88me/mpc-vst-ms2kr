#!/usr/bin/env python3
"""The MS2KR skin: every page drawn here (PIL) at the MPC's 1280 x 628 in the look of the real MS2000R panel (colours sampled from
docs/reference/ms2000r-panel-photo.png; section names, key names and inverse sub-labels as printed on the unit, after upstream's
source/gui/vector_panel.h; no maker's logo or model lettering). Live controls go over the drawn sockets and keys.
    make_skin.py      writes vst/layout.conf, vst/images/ (pages, knob strip, keys, tile)
The LCD (lcd1/lcd2) is on every page: the firmware shows the value of whatever is moved there, so knobs carry no value text."""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
VST = os.path.join(HERE, "..", "vst")
IMG = os.path.join(VST, "images")
FONT = os.path.join(VST, "fonts")
os.makedirs(IMG, exist_ok=True)
Y86 = 86
W, H = 1280, 628

PANEL = (41, 76, 99)          # the R's steel blue (photo: #27495f, lifted a little for the MPC screen)
PANEL_DK = (30, 57, 76)
LINE = (214, 226, 232)        # printed frame lines
INK = (238, 243, 245)         # printed text
INK_DIM = (170, 190, 202)
INV_BG = (206, 220, 226)      # the inverse (shift / vocoder) labels
INV_FG = PANEL
CREAM = (214, 201, 179)       # program keys
BLACK = (41, 36, 34)
RED = (224, 66, 26)           # WRITE
LCD_BG = (150, 168, 64)
LCD_INK = (28, 36, 10)
LED_ON = (255, 60, 30)
SOCK = 76                     # knob size on screen

PARAMS = {p["key"]: p for p in json.load(open(os.path.join(VST, "params.json")))["params"]}
_fonts = {}


def F(size, bold=True):
    """Ubuntu Sans (Ubuntu Font Licence), the variable font at its condensed width: close to the panel's condensed lettering"""
    if (size, bold) not in _fonts:
        f = ImageFont.truetype(os.path.join(FONT, "UbuntuSans.ttf"), size)
        axes = {a["name"]: a for a in f.get_variation_axes()}
        f.set_variation_by_axes([75 if n in (b"Width", "Width") else (700 if bold else 450) for n in [a["name"] for a in f.get_variation_axes()]])
        _fonts[(size, bold)] = f
    return _fonts[(size, bold)]


# ---------------------------------------------------------------- assets
def knob_strip():
    """101 frames, 104 px: knurled black skirt, dark cap, white pointer; -135..+135 degrees (up = middle)"""
    S, n, big = 104, 101, 416
    out = Image.new("RGBA", (S, S * n))
    for i in range(n):
        a = math.radians(-135 + 270 * i / (n - 1))
        im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c, R = big / 2, big * 0.46
        d.ellipse((c - R + 10, c - R + 14, c + R + 10, c + R + 14), fill=(8, 14, 20, 120))          # shadow
        d.ellipse((c - R, c - R, c + R, c + R), fill=(22, 22, 24, 255))                                # skirt
        for k in range(36):                                                                            # knurl, turns with the knob
            t = a + k * math.pi / 18
            x0, y0 = c + math.sin(t) * R * 0.80, c - math.cos(t) * R * 0.80
            x1, y1 = c + math.sin(t) * R * 0.98, c - math.cos(t) * R * 0.98
            d.line((x0, y0, x1, y1), fill=(58, 58, 62, 255), width=6)
        r2 = R * 0.72
        d.ellipse((c - r2, c - r2, c + r2, c + r2), fill=(46, 47, 51, 255))                           # cap
        d.ellipse((c - r2 + 8, c - r2 + 8, c + r2 - 8, c + r2 - 8), outline=(64, 65, 70, 255), width=4)
        d.line((c + math.sin(a) * R * 0.18, c - math.cos(a) * R * 0.18, c + math.sin(a) * R * 0.95, c - math.cos(a) * R * 0.95),
               fill=(245, 245, 240, 255), width=16)                                                    # pointer
        out.paste(im.resize((S, S), Image.LANCZOS), (0, i * S))
    out.save(os.path.join(IMG, "knob_ms2k.png"))


def key_img(name, face, w, h, lit=False):
    big = 4
    im = Image.new("RGBA", (w * big, h * big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 10, w * big - 2, h * big - 2), 14, fill=(10, 20, 28, 170))                    # shadow
    d.rounded_rectangle((0, 0, w * big - 8, h * big - 10), 14, fill=face)
    hi = tuple(min(255, v + 34) for v in face)
    d.rounded_rectangle((8, 8, w * big - 16, (h * big) * 0.42), 10, fill=hi)                              # top sheen
    if lit:   # pressed: the face goes down a little and the LED slit glows
        d.rounded_rectangle((0, 0, w * big - 8, h * big - 10), 14, outline=LED_ON, width=10)
    im.resize((w, h), Image.LANCZOS).save(os.path.join(IMG, name))


def tile():
    t = Image.new("RGB", (270, 110), PANEL)
    d = ImageDraw.Draw(t)
    d.rectangle((6, 6, 263, 103), outline=LINE, width=2)
    d.text((135, 46), "MS2KR", font=F(46), fill=INK, anchor="mm")
    d.text((135, 84), "ANALOG MODELING", font=F(15, False), fill=INK_DIM, anchor="mm")
    t.save(os.path.join(IMG, "tile.png"))


knob_strip()
key_img("key_black.png", BLACK, 92, 42); key_img("key_black_on.png", BLACK, 92, 42, True)
key_img("key_cream.png", CREAM, 92, 42); key_img("key_cream_on.png", CREAM, 92, 42, True)
key_img("key_red.png", RED, 92, 42); key_img("key_red_on.png", RED, 92, 42, True)
key_img("pad_cream.png", CREAM, 64, 58); key_img("pad_cream_on.png", CREAM, 64, 58, True)
tile()

lines = []
emit = lines.append


class Page:
    def __init__(self, name, qkeys):
        self.name, self.qkeys = name, qkeys
        self.im = Image.new("RGB", (W, H), PANEL)
        self.d = ImageDraw.Draw(self.im)
        self.widgets = []
        self.header()

    # ---- drawing
    def text(self, x, y, s, size=18, color=INK, bold=True, anchor="ma"):
        self.d.text((x, y), s, font=F(size, bold), fill=color, anchor=anchor)

    def inverse(self, cx, y, s, size=14):
        f = F(size)
        tw = f.getlength(s)
        self.d.rectangle((cx - tw / 2 - 4, y - 1, cx + tw / 2 + 4, y + size + 3), fill=INV_BG)
        self.text(cx, y, s, size, INV_FG)

    def frame(self, x, y, w, h, title=""):
        """a section as printed: thin light frame, the name above it"""
        d = self.d
        d.rectangle((x, y, x + w, y + h), outline=LINE, width=2)
        if title:
            f = F(22)
            tw = f.getlength(title)
            d.rectangle((x + w / 2 - tw / 2 - 10, y - 14, x + w / 2 + tw / 2 + 10, y + 12), fill=PANEL)
            self.text(x + w / 2, y - 13, title, 22)

    def header(self):
        """every page: wordmark, the LCD (two lines) and the program stepper"""
        d = self.d
        d.rectangle((0, 0, W, 104), fill=PANEL_DK)
        d.line((0, 104, W, 104), fill=LINE, width=2)
        self.text(26, 18, "MS2KR", 40, INK, True, "la")
        self.text(28, 66, "ANALOG MODELING SYNTHESIZER", 14, INK_DIM, False, "la")
        d.rounded_rectangle((300, 8, 760, 98), 6, fill=(16, 18, 18))                         # LCD bezel
        d.rectangle((310, 16, 750, 90), fill=LCD_BG)
        self.widgets.append('readout cx=530 cy=%d w=430 h=34 label="" key=lcd1 style=dotmatrix tsize=27 talign=left' % (34 + Y86))
        self.widgets.append('readout cx=530 cy=%d w=430 h=34 label="" key=lcd2 style=dotmatrix tsize=27 talign=left' % (72 + Y86))
        self.text(1020, 6, "PROGRAM", 15, INK_DIM)
        self.widgets.append('stepper w=480 h=46 cx=1020 cy=%d label="" key=program get=program_name prev=prog_prev next=prog_next '
                            'style=dotmatrix persistent=1' % (54 + Y86))

    # ---- controls
    def knob(self, cx, cy, key, label, inv=None):
        self.text(cx, cy - SOCK // 2 - 36, label, 16)
        if inv and inv.replace(" ", "") != label.replace(" ", ""):
            self.inverse(cx, cy - SOCK // 2 - 17, inv, 13)
        for k in range(11):                                                                    # the printed scale
            t = math.radians(-135 + 27 * k)
            r0, r1 = SOCK / 2 + 4, SOCK / 2 + (10 if k in (0, 5, 10) else 7)
            self.d.line((cx + math.sin(t) * r0, cy - math.cos(t) * r0, cx + math.sin(t) * r1, cy - math.cos(t) * r1), fill=LINE, width=2)
        self.widgets.append('knob cx=%d cy=%d r=%d label="" key=%s ns=0 vs=0' % (cx, cy + Y86, SOCK // 2, key))

    def key(self, cx, cy, key, label, face="black", inv=None, led=None, w=92, h=42, cap="", lw=150):
        """a panel key; led = a LED group's text (engine led_*) shown under it, as the LEDs beside the key on the unit"""
        if label:
            self.text(cx, cy - h // 2 - 22, label, 15)
        if inv and inv.replace(" ", "") != label.replace(" ", ""):
            self.inverse(cx, cy - h // 2 - 40, inv, 12)
        self.widgets.append('button cx=%d cy=%d w=%d h=%d label="%s" key=%s img=images/key_%s.png img_on=images/key_%s_on.png'
                            % (cx, cy + Y86, w, h, cap, key, face, face))
        if led:
            # the LED window: big enough to read at a glance (2026-11-03, user: "the little readouts could be bigger")
            self.d.rounded_rectangle((cx - lw // 2, cy + h // 2 + 6, cx + lw // 2, cy + h // 2 + 44), 5, fill=(18, 30, 40))
            self.widgets.append('readout cx=%d cy=%d w=%d h=36 label="" key=%s tsize=23 tweight=bold tcolor=ff5a3a' % (cx, cy + h // 2 + 25 + Y86, lw - 6, led))

    def readout(self, cx, cy, key, label, w=260, h=30):
        self.text(cx, cy - h // 2 - 22, label, 15, INK_DIM)
        self.d.rounded_rectangle((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2), 4, fill=(18, 30, 40))
        self.widgets.append('readout cx=%d cy=%d w=%d h=%d label="" key=%s tsize=18 tcolor=d6e2e8' % (cx, cy + Y86, w - 8, h, key))

    def done(self):
        fn = "images/page_%s.png" % self.name.replace(" ", "_").replace("/", "_")
        self.im.save(os.path.join(VST, fn))
        emit("")
        emit("[tab %s]" % self.name)
        emit('art x=0 y=%d w=%d h=%d file="%s"' % (Y86, W, H, fn))
        lines.extend(self.widgets)
        emit('qlinks "%s" = %s' % (self.name, ",".join(self.qkeys)))


def spread(x0, x1, n):
    cw = (x1 - x0) / n
    return [int(x0 + cw * (i + 0.5)) for i in range(n)]


emit("""# MS2KR skin layout: generated by tools/make_skin.py (edit that, not this file).
theme_bg=294c63
theme_panel=294c63
theme_line=d6e2e8
theme_ink=eef3f5
theme_ink_dim=aabeca
theme_accent=ff5a3a
theme_accent_hi=ff8a6a
theme_knob_face=2e2f33
theme_knob_ring=16161a
theme_knob_dot=f5f5f0
theme_lcd=12202a
theme_box=12202a
theme_btn_bg=29221f
theme_btn_text=eef3f5
theme_btn_text_plain=eef3f5
theme_display_bg=96a840
theme_display_cell=96a840
theme_display_off=96a840
theme_display_bezel=101212
theme_display_ink=1c240a
style=td3
knob_strip=images/knob_ms2k.png
qlink_bounds=column""")

# ---------------------------------------------------------------- PLAY
p = Page("PLAY", ["program", "vol", "out_level"])
p.frame(16, 136, 300, 230, "POWER / VOLUME")
p.knob(90, 250, "vol", "VOLUME")
p.knob(240, 250, "out_level", "OUTPUT %")
p.key(166, 334, "panic", "", "black", w=120, cap="PANIC")
p.frame(336, 136, 396, 230, "STATUS")
p.readout(534, 210, "status", "ENGINE", 360)
p.readout(534, 296, "led_orig", "ORIGINAL VALUE", 240, 36)
# the edit block, placed as on the unit (right of the LCD)
p.frame(752, 136, 512, 230, "")
xs = spread(760, 1256, 4)
p.text((xs[0] + xs[1]) // 2, 140, "CURSOR", 15)
p.key(xs[0], 186, "k_curl", "<", "cream"); p.key(xs[1], 186, "k_curr", ">", "cream")
p.key(xs[2], 186, "k_no", "- / NO", "cream"); p.key(xs[3], 186, "k_yes", "+ / YES", "cream")
p.text((xs[0] + xs[1]) // 2, 226, "PAGE", 15)
p.key(xs[0], 270, "k_pagem", "-", "cream"); p.key(xs[1], 270, "k_pagep", "+", "cream")
p.key(xs[3], 270, "k_write", "WRITE", "red")
p.key(xs[0], 340, "k_edit", "EDIT", "cream"); p.key(xs[1], 340, "k_global", "GLOBAL", "cream")
p.inverse((xs[1] + xs[2]) // 2 + 30, 300, "COMPARE / DEMO", 12)
p.key(xs[3], 340, "k_exit", "EXIT", "cream")
# the 16 program keys, with their EDIT-mode page names (as printed under them)
p.frame(16, 404, 1248, 210, "PROGRAM / EDIT KEYS")
names = [("COMMON", "COMMON"), ("VOICE", "VOICE"), ("PITCH", "PITCH"), ("OSC 1", "OSC 1"), ("OSC 2", "AUDIO IN 2"), ("FILTER", "FILTER"), ("AMP", "AMP"),
         ("EG", "EG"), ("LFO", "LFO"), ("PATCH", "CH LEVEL"), ("SEQ", "CH PAN"), ("MOD FX", "MOD FX"), ("DELAY FX", "DELAY FX"), ("EQ", "EQ"),
         ("ARPEGGIO", "ARPEGGIO"), ("UTILITY", "UTILITY")]
for i, x in enumerate(spread(24, 1256, 16)):
    p.text(x, 432, str(i + 1), 18)
    p.widgets.append('button cx=%d cy=%d w=64 h=58 label="" key=k_pad%d img=images/pad_cream.png img_on=images/pad_cream_on.png' % (x, 492 + Y86, i + 1))
    p.text(x, 530, names[i][0], 12)
    p.inverse(x, 550, names[i][1], 11)
p.text(640, 580, "EDIT: the keys select the edit pages, PAGE +/- the parameters, the LCD shows the value", 14, INK_DIM, False)
p.done()

# ---------------------------------------------------------------- BANKS
p = Page("BANKS", ["program", "-", "-", "-"])
p.frame(16, 136, 220, 476, "BANK")
p.widgets.append('list x=30 y=%d w=192 h=440 cols=1 rows=8 gap=6 th=48 key=bank_slot' % (156 + Y86))
p.frame(256, 136, 820, 476, "PROGRAM")
p.widgets.append('list x=270 y=%d w=792 h=440 cols=2 rows=8 gap=6 th=48 key=patch_slot order=cols' % (156 + Y86))
p.frame(1096, 136, 168, 476, "FAVOURITES")
p.key(1180, 230, "fav_save", "", "black", w=130, h=52, cap="+ FAV")
p.key(1180, 370, "fav_delete", "", "black", w=130, h=52, cap="- FAV")
p.text(1180, 470, "MPC PRESET", 13, INK_DIM, False)
p.text(1180, 488, "menu lists", 13, INK_DIM, False)
p.text(1180, 506, "the favourites", 13, INK_DIM, False)
p.done()

# ---------------------------------------------------------------- OSC
p = Page("OSC", ["o1c1", "o1c2", "o2semi", "o2tune", "mx1", "mx2", "mxn", "porta"])
p.frame(16, 136, 410, 476, "OSCILLATOR 1")
p.key(221, 236, "k_o1wave", "WAVE", led="led_o1wave", lw=220)
k1 = spread(24, 418, 2)
p.knob(k1[0], 476, "o1c1", "CONTROL 1", "CONTROL 1"); p.knob(k1[1], 476, "o1c2", "CONTROL 2", "CONTROL 2")
p.frame(442, 136, 410, 476, "OSCILLATOR 2")
k2 = spread(450, 844, 2)
p.key(k2[0], 236, "k_o2wave", "WAVE", led="led_o2wave", lw=170); p.key(k2[1], 236, "k_o2mod", "OSC MOD", led="led_o2mod", lw=170)
p.text(647, 368, "OSC 2 PITCH", 15, INK_DIM)
p.knob(k2[0], 476, "o2semi", "SEMITONE", "HPF LEVEL"); p.knob(k2[1], 476, "o2tune", "TUNE", "THRESHOLD")
p.frame(868, 136, 396, 300, "MIXER")
km = spread(876, 1256, 3)
p.knob(km[0], 330, "mx1", "OSC 1", "OSC 1"); p.knob(km[1], 330, "mx2", "OSC 2", "INST"); p.knob(km[2], 330, "mxn", "NOISE", "NOISE")
p.frame(868, 452, 186, 160, "PORTAMENTO")
p.knob(961, 556, "porta", "TIME", "TIME")
p.frame(1070, 452, 194, 160, "TIMBRE")
p.key(1167, 510, "k_timbre", "SELECT", "cream", led="led_timbre", lw=120)
p.done()

# ---------------------------------------------------------------- FILTER / AMP / EG
p = Page("FILTER / EG", ["cut", "res", "eg1int", "kbdtr", "lvl", "pan", "-", "-", "eg1a", "eg1d", "eg1s", "eg1r", "eg2a", "eg2d", "eg2s", "eg2r"])
p.frame(16, 136, 740, 214, "FILTER")
kf = spread(24, 600, 4)
p.knob(kf[0], 262, "cut", "CUTOFF", "CUTOFF"); p.knob(kf[1], 262, "res", "RESONANCE", "RESONANCE")
p.knob(kf[2], 262, "eg1int", "EG 1 INT", "FC MOD INT"); p.knob(kf[3], 262, "kbdtr", "KBD TRACK", "E.F.SENSE")
p.key(680, 226, "k_ftype", "FILTER TYPE", inv="FORMANT SHIFT", led="led_ftype", lw=140)
p.frame(772, 136, 492, 214, "AMP")
p.knob(830, 262, "lvl", "LEVEL", "LEVEL"); p.knob(935, 262, "pan", "PAN", "DIRECT LEVEL")
p.key(1063, 226, "k_eg2gate", "EG 2 / GATE", led="led_eg2gate", lw=130); p.key(1196, 226, "k_dist", "DISTORTION", led="led_dist", lw=130)
p.frame(16, 386, 616, 226, "EG 1 (FILTER)")
for x, k, n in zip(spread(24, 624, 4), ("eg1a", "eg1d", "eg1s", "eg1r"), ("ATTACK", "DECAY", "SUSTAIN", "RELEASE")):
    p.knob(x, 516, k, n, n)
p.frame(648, 386, 616, 226, "EG 2 (AMP)")
for x, k, n in zip(spread(656, 1256, 4), ("eg2a", "eg2d", "eg2s", "eg2r"), ("ATTACK", "DECAY", "SUSTAIN", "RELEASE")):
    p.knob(x, 516, k, n, n)
p.done()

# ---------------------------------------------------------------- LFO / FX / PATCH
p = Page("LFO / FX / PATCH", ["lfo1f", "lfo2f", "fxspd", "fxdep", "patch1", "patch2", "patch3", "patch4"])
p.frame(16, 136, 200, 476, "LFO 1")
p.key(116, 232, "k_lfo1", "SELECT", inv="SELECT", led="led_lfo1", lw=150)
p.knob(116, 470, "lfo1f", "FREQUENCY", "FREQUENCY")
p.frame(232, 136, 200, 476, "LFO 2")
p.key(332, 232, "k_lfo2", "SELECT", inv="SELECT", led="led_lfo2")
p.knob(332, 470, "lfo2f", "FREQUENCY", "FREQUENCY")
p.frame(448, 136, 300, 476, "EFFECTS")
p.key(598, 232, "k_fxsel", "MOD / DELAY", inv="MOD / DELAY", led="led_fx")
kx = spread(456, 740, 2)
p.knob(kx[0], 470, "fxspd", "SPEED/TIME", "SPEED / TIME"); p.knob(kx[1], 470, "fxdep", "DEPTH/FDBK", "DEPTH / FEEDBACK")
p.frame(764, 136, 500, 476, "VIRTUAL PATCH")
kv = spread(772, 1256, 3)
p.key(kv[0], 232, "k_vpsel", "SELECT", led="led_vpsel", lw=150); p.key(kv[1], 232, "k_vpsrc", "SOURCE", inv="FC MOD SOURCE", led="led_vpsrc", lw=150)
p.key(kv[2], 232, "k_vpdst", "DESTINATION", led="led_vpdst", lw=150)
for x, k in zip(spread(772, 1256, 4), ("patch1", "patch2", "patch3", "patch4")):
    p.knob(x, 470, k, "PATCH " + k[-1])
p.done()

# ---------------------------------------------------------------- ARP / SEQ / KEYBOARD
p = Page("ARP / SEQ", ["tempo", "gate", "-", "-"])
p.frame(16, 136, 760, 260, "ARPEGGIATOR")
p.knob(84, 270, "tempo", "TEMPO"); p.knob(196, 270, "gate", "GATE")
ka = spread(250, 772, 4)
p.key(ka[0], 250, "k_arpon", "ON / OFF", led="led_arp", lw=122); p.key(ka[1], 250, "k_arplat", "LATCH", led="led_latch", lw=122)
p.key(ka[2], 250, "k_arprng", "RANGE"); p.key(ka[3], 250, "k_arptyp", "TYPE")
p.text((ka[2] + ka[3]) // 2, 300, "1-4 OCTAVE   UP DOWN ALT1 ALT2 RANDOM TRIGGER", 13, INK_DIM, False)
p.frame(792, 136, 472, 260, "MOD SEQUENCE")
km = spread(800, 1256, 3)
p.key(km[0], 250, "k_mseqon", "ON / OFF", led="led_mseq", lw=140); p.key(km[1], 250, "k_mseqrec", "REC", "cream", led="led_mrec", lw=140)
p.key(km[2], 250, "k_seqsel", "SEQ EDIT", "cream", inv="CH PARAM", led="led_seq", lw=140)
p.frame(16, 432, 600, 180, "KEYBOARD")
p.key(166, 520, "k_kbd", "KEYBOARD", "cream", led="led_kbd")
p.text(420, 500, "plays the program keys", 14, INK_DIM, False)
p.text(420, 520, "as a keyboard", 14, INK_DIM, False)
p.frame(632, 432, 632, 180, "BANK / OCTAVE")
kb = spread(640, 1256, 2)
p.key(kb[0], 520, "k_bankdn", "DOWN", "cream"); p.key(kb[1], 520, "k_bankup", "UP", "cream")
p.done()

open(os.path.join(VST, "layout.conf"), "w").write("\n".join(lines) + "\n")
print("layout.conf + %d images" % len(os.listdir(IMG)))
