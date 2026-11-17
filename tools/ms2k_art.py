#!/usr/bin/env python3
"""The art library of the MS2KR skin: everything is drawn from code (Pillow, no numpy), after the MS2000R's front panel and the
MS2KxR editor: a metallic blue-teal panel with printed white lines and captions, knurled charcoal knobs with a white pointer, black and
cream keys, the 16 square program keys, the green LCD. The page layouts are in make_tui.py / mock_pages.py: a restyle is this file.

Light comes from the upper left; every shaded part is computed per pixel at 3x and scaled down."""
import math, os, random
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIT = os.path.join(ROOT, "tools", "fonts", "TitilliumWeb-SemiBold.ttf")
TIT_B = os.path.join(ROOT, "tools", "fonts", "TitilliumWeb-Bold.ttf")

TEAL = (36, 98, 126)             # the panel
TEAL_HI = (52, 124, 154)
TEAL_LO = (24, 70, 96)
INK = (226, 238, 242)            # printed white
INK_DIM = (176, 200, 210)
LINE = (214, 230, 236)
AMBER = (255, 96, 56)            # LED text
LCD_BG = (150, 176, 62)
LCD_HI = (176, 200, 84)
LCD_LO = (112, 140, 40)
LCD_INK = (28, 40, 10)
SHADOW = (6, 22, 34)
LIGHT = (-0.5, -0.6, 0.62)       # from the upper left (screen y down), towards the viewer

_fonts = {}


def F(size, bold=True):
    k = (size, bold)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(TIT_B if bold else TIT, size)
    return _fonts[k]


def fit(text, size, width, bold=True):
    while size > 9 and F(size, bold).getlength(text) > width:
        size -= 1
    return F(size, bold)


def _norm(v):
    l = math.sqrt(sum(x * x for x in v))
    return tuple(x / l for x in v)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


# ---- the panel -------------------------------------------------------------------------------------------------------------
def panel(w=1280, h=628, seed=3):
    """Blue-teal anodised metal: a soft top-left light, a darker foot, fine metallic flake and a faint horizontal grain."""
    base = Image.new("RGB", (w, h))
    px = base.load()
    for y in range(h):
        for x in range(0, w):
            u, v = x / w, y / h
            t = 0.55 * (1 - u) * 0.6 + 0.45 * (1 - v) * 0.7        # lit from the upper left
            px[x, y] = lerp(TEAL_LO, TEAL_HI, min(1.0, max(0.0, t)))
    rnd = random.Random(seed)
    flake = Image.effect_noise((w, h), 70).convert("L")           # sparkle: only the brightest specks, slightly blurred
    flake = flake.point(lambda p: 255 if p > 246 else (70 if p > 238 else 0)).filter(ImageFilter.GaussianBlur(0.6))
    grain = Image.effect_noise((w, h), 18).convert("L").filter(ImageFilter.GaussianBlur(0.7))
    grain = ImageChops.offset(grain, 0, 0)
    im = base.convert("RGBA")
    fl = Image.new("RGBA", (w, h), (214, 236, 246, 0))
    fl.putalpha(flake.point(lambda p: int(p * 0.28)))
    im.alpha_composite(fl)
    g = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    g.putalpha(grain.point(lambda p: max(0, p - 132) // 7))
    im.alpha_composite(g)
    dk = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dk.putalpha(grain.point(lambda p: max(0, 124 - p) // 8))
    im.alpha_composite(dk)
    return im


def engrave(im, box, r=3, width=2, colour=LINE, alpha=215):
    """A printed rectangle: a white line with a faint dark edge below it, so it sits on the panel."""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x0 + 1, y0 + 1, x1 + 1, y1 + 1), r, outline=SHADOW + (70,), width=width)
    d.rounded_rectangle(box, r, outline=colour + (alpha,), width=width)


def section(im, x0, y0, x1, y1, title, size=19):
    """A panel section: a printed frame with its title centred in a gap of the top edge (white caps)."""
    f = F(size, True)
    tw = int(f.getlength(title)) + 22
    cx = (x0 + x1) // 2
    engrave(im, (x0, y0, x1, y1))
    gap = Image.new("RGBA", (tw, 6), (0, 0, 0, 0))
    # re-paint the panel under the gap by copying from just above the frame, so the title breaks the line
    im.paste(im.crop((cx - tw // 2, y0 - 12, cx + tw // 2, y0 - 6)).resize((tw, 12)), (cx - tw // 2, y0 - 4))
    d = ImageDraw.Draw(im)
    d.text((cx + 1, y0 + 1), title, font=f, fill=SHADOW + (110,), anchor="mm")
    d.text((cx, y0), title, font=f, fill=INK + (255,), anchor="mm")


def caption(im, cx, cy, text, size=15, colour=INK, width=120):
    f = fit(text, size, width)
    d = ImageDraw.Draw(im)
    d.text((cx + 1, cy + 1), text, font=f, fill=SHADOW + (90,), anchor="mm")
    d.text((cx, cy), text, font=f, fill=colour + (255,), anchor="mm")


def pill(im, cx, cy, text, size=12, width=96):
    """the dark boxed second caption of the panel (the vocoder / alternate function)"""
    f = fit(text, size, width - 10)
    w = int(f.getlength(text)) + 12
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((cx - w // 2, cy - 9, cx + w // 2, cy + 9), 3, fill=(20, 52, 70, 255))
    d.rounded_rectangle((cx - w // 2, cy - 9, cx + w // 2, cy + 9), 3, outline=(120, 160, 176, 200))
    d.text((cx, cy), text, font=f, fill=INK + (255,), anchor="mm")


def ticks(im, cx, cy, r, n=11):
    """the printed scale round a knob: fine radial ticks over 270 degrees, longer at the ends and the middle"""
    d = ImageDraw.Draw(im)
    for i in range(n):
        a = math.radians(135 + 270 * i / (n - 1))
        big = i in (0, n // 2, n - 1)
        r0, r1 = r, r + (7 if big else 4)
        x0, y0, x1, y1 = cx + math.cos(a) * r0, cy + math.sin(a) * r0, cx + math.cos(a) * r1, cy + math.sin(a) * r1
        d.line((x0 + 1, y0 + 1, x1 + 1, y1 + 1), fill=SHADOW + (90,), width=2)
        d.line((x0, y0, x1, y1), fill=INK + (235,), width=2 if big else 1)


def well(im, x0, y0, x1, y1, r=6):
    """a recess in the panel (a dark window for a readout)"""
    S = 3
    w, h = x1 - x0, y1 - y0
    lay = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), r * S, fill=(8, 22, 32, 255))
    inner = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(inner).rounded_rectangle((2 * S, 3 * S, w * S - 2 * S, h * S - 2 * S), r * S, fill=(14, 36, 50, 255))
    lay.alpha_composite(inner)
    lay = lay.resize((w, h), Image.LANCZOS)
    hl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle((0, 0, w - 1, h - 1), r, outline=(150, 190, 206, 90), width=1)
    im.alpha_composite(lay, (x0, y0))
    im.alpha_composite(hl, (x0, y0))


# ---- knobs -------------------------------------------------------------------------------------------------------------------
def _knob_layers(size, rib_phase):
    """The MS2000's knob from above: a dark knurled skirt (ribs turning with the knob) and a flat charcoal top with a bright turned edge."""
    S = 3
    n = size * S
    R = n / 2.0 - 7 * S
    cx = cy = n / 2.0 - 1 * S
    L = _norm(LIGHT)
    H = _norm((L[0], L[1], L[2] + 1.0))
    RT = 0.70                                  # the top's radius (of R)
    NR = 36                                    # ribs round the skirt
    skirt = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    top = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ps, pt = skirt.load(), top.load()
    la = math.atan2(L[1], L[0])
    for y in range(n):
        for x in range(n):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            r = math.hypot(dx, dy) / R
            if r > 1.0:
                continue
            th = math.atan2(dy, dx)
            if r >= RT:
                k = (r - RT) / (1 - RT)
                rib = 0.5 + 0.5 * math.cos(NR * th + rib_phase)               # a rib crest = 1
                # a rib's flank faces towards or away from the light: shade by where the crest's normal points
                nxy = 0.8 - 0.35 * k
                nx, ny = math.cos(th) * nxy, math.sin(th) * nxy
                nx += -math.sin(th) * 0.45 * math.sin(NR * th + rib_phase)
                ny += math.cos(th) * 0.45 * math.sin(NR * th + rib_phase)
                nn = _norm((nx, ny, 0.55 - 0.3 * k))
                dif = max(0.0, sum(a * b for a, b in zip(nn, L)))
                spc = max(0.0, sum(a * b for a, b in zip(nn, H))) ** 14
                g = (16 + 56 * dif + 70 * spc) * (0.78 + 0.22 * rib) * (1 - 0.55 * max(0.0, (r - 0.95) / 0.05))
                ps[x, y] = (int(g * 0.98), int(g), int(g * 1.04), 255)
            else:
                q = r / RT
                lin = 1.10 - 0.22 * ((dx + dy) / (2 * R * RT) + 0.5)
                # spin-turned aluminium: a soft two-lobed sheen that does not turn, and fine concentric rings
                sheen = 0.5 + 0.5 * math.cos(2 * (th - la))
                ring = 0.96 + 0.04 * math.cos(q * 70)
                g = (40 + 12 * sheen) * lin * ring
                if q > 0.90:                                          # the turned edge: bright where it faces the light
                    e = (q - 0.90) / 0.10
                    face = 0.5 + 0.5 * math.cos(th - la)
                    g = g * (1 - e) + (70 + 150 * face) * e
                pt[x, y] = (int(g), int(g * 1.01), int(g * 1.05), 255)
    sh = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((cx - R + 2 * S, cy - R + 4 * S, cx + R + 3 * S, cy + R + 6 * S), fill=SHADOW + (150,))
    sh = sh.filter(ImageFilter.GaussianBlur(3 * S))
    return sh, skirt, top, (cx, cy, R, RT)


def knob_strip(size=84, frames=101, bipolar=False):
    """The knob as a film strip, -135 .. +135 degrees over the frames: a knurled skirt (turning), a flat top, a white pointer line."""
    S = 3
    n = size * S
    PH = 8
    layers = [_knob_layers(size, 2 * math.pi * p / PH) for p in range(PH)]
    sh, _, _, (cx, cy, R, RT) = layers[0]
    out = Image.new("RGBA", (size, size * frames), (0, 0, 0, 0))
    for f in range(frames):
        t = f / (frames - 1)
        rot = math.radians(-135 + 270 * t - 90)                           # 0 = straight up at t = 0.5
        phase = int(round((rot * 36 / (2 * math.pi)) % 1.0 * PH)) % PH    # which skirt render is nearest this turn
        _, skirt, top, _ = layers[phase]
        im = sh.copy()
        im.alpha_composite(skirt)
        im.alpha_composite(top)
        d = ImageDraw.Draw(im)
        ux, uy = math.cos(rot), math.sin(rot)
        x0, y0 = cx + ux * R * 0.10, cy + uy * R * 0.10
        x1, y1 = cx + ux * R * (RT - 0.06), cy + uy * R * (RT - 0.06)
        d.line((x0 + 1.4 * S, y0 + 1.8 * S, x1 + 1.4 * S, y1 + 1.8 * S), fill=(0, 0, 0, 120), width=int(3.4 * S))
        d.line((x0, y0, x1, y1), fill=(244, 246, 244, 255), width=int(2.8 * S))
        out.paste(im.resize((size, size), Image.LANCZOS), (0, f * size))
    return out


# ---- keys --------------------------------------------------------------------------------------------------------------------
def key(w, h, kind="black", pressed=False):
    """A panel key: black, cream or red, a soft shadow, a rounded body shaded top to bottom and a bright edge on the lit side; pressed = pushed in."""
    S = 3
    pad = 6
    W, H = (w + 2 * pad) * S, (h + 2 * pad) * S
    cols = {"black": ((70, 72, 78), (26, 27, 30), (150, 154, 162)),
            "cream": ((238, 236, 226), (186, 184, 172), (255, 255, 250)),
            "red": ((236, 72, 52), (150, 24, 16), (255, 170, 150))}[kind]
    top, bot, edge = cols
    dy = 2 if pressed else 0
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    sx = (1 if pressed else 2) * S
    d.rounded_rectangle((pad * S + sx, pad * S + sx + 2 * S, (pad + w) * S + sx, (pad + h) * S + sx + 2 * S), 6 * S, fill=SHADOW + (150,))
    lay = lay.filter(ImageFilter.GaussianBlur(2.5 * S))
    d = ImageDraw.Draw(lay)
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bp = body.load()
    x0, y0, x1, y1 = pad * S, (pad + dy) * S, (pad + w) * S, (pad + h + dy) * S
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((x0, y0, x1, y1), 6 * S, fill=255)
    mp = mask.load()
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0)
        c = lerp(top, bot, t ** 0.9 * (1.15 if pressed else 1.0))
        for x in range(x0, x1):
            if mp[x, y]:
                bp[x, y] = c + (255,)
    lay.alpha_composite(body)
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x0, y0, x1, y1), 6 * S, outline=lerp(bot, (0, 0, 0), 0.5) + (200,), width=S)
    # the bright edge on the lit sides, and a dark one at the foot
    d.arc((x0, y0, x0 + 12 * S, y0 + 12 * S), 180, 270, fill=edge + (190,), width=int(1.5 * S))
    d.line((x0 + 6 * S, y0 + S, x1 - 6 * S, y0 + S), fill=edge + (170 if kind != "black" else 130,), width=int(1.5 * S))
    d.line((x0 + S, y0 + 6 * S, x0 + S, y1 - 6 * S), fill=edge + (90,), width=S)
    # the finger dip: a faint darker band across the top face
    sheen = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).rounded_rectangle((x0 + 4 * S, y0 + 3 * S, x1 - 4 * S, y0 + 9 * S), 3 * S, fill=(255, 255, 255, 30 if kind == "black" else 60))
    sheen = Image.composite(sheen, Image.new("RGBA", (W, H), (0, 0, 0, 0)), mask)
    lay.alpha_composite(sheen.filter(ImageFilter.GaussianBlur(S)))
    return lay.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS)


def pad(w, h, framed, lit):
    """One of the 16 square program keys: a pale translucent cap (a silver frame on the odd ones), lit = backlit warm white."""
    S = 3
    m = 8
    W, H = (w + 2 * m) * S, (h + 2 * m) * S
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((m * S + 2 * S, m * S + 4 * S, (m + w) * S + 2 * S, (m + h) * S + 4 * S), 4 * S, fill=SHADOW + (150,))
    lay = lay.filter(ImageFilter.GaussianBlur(3 * S))
    d = ImageDraw.Draw(lay)
    x0, y0, x1, y1 = m * S, m * S, (m + w) * S, (m + h) * S
    if lit:
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((x0 - 2 * S, y0 - 2 * S, x1 + 2 * S, y1 + 2 * S), 8 * S, fill=(255, 226, 150, 120))
        lay.alpha_composite(glow.filter(ImageFilter.GaussianBlur(5 * S)))
        d = ImageDraw.Draw(lay)
    if framed:    # a raised silver bezel round the cap
        for i in range(7):
            t = i / 6
            c = lerp((214, 214, 206), (140, 144, 140), t)
            d.rounded_rectangle((x0 + i * S // 2, y0 + i * S // 2, x1 - i * S // 2, y1 - i * S // 2), 4 * S, outline=c + (255,), width=S // 2 + 1)
        ix = 4 * S
    else:
        ix = 0
    cap = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cp = cap.load()
    mk = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mk).rounded_rectangle((x0 + ix, y0 + ix, x1 - ix, y1 - ix), 3 * S, fill=255)
    mp = mk.load()
    ctop, cbot = ((255, 248, 226), (238, 216, 168)) if lit else ((230, 232, 230), (176, 180, 178))
    for y in range(y0 + ix, y1 - ix):
        t = (y - (y0 + ix)) / max(1, (y1 - y0 - 2 * ix))
        for x in range(x0 + ix, x1 - ix):
            if mp[x, y]:
                u = (x - x0) / (x1 - x0)
                cp[x, y] = lerp(lerp(ctop, cbot, t), (255, 255, 255), 0.10 * (1 - u) * (1 - t)) + (255,)
    lay.alpha_composite(cap)
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x0 + ix, y0 + ix, x1 - ix, y1 - ix), 3 * S, outline=(90, 94, 92, 200), width=S // 2 + 1)
    d.line((x0 + ix + 3 * S, y0 + ix + S, x1 - ix - 3 * S, y0 + ix + S), fill=(255, 255, 255, 190), width=S)
    return lay.resize((w + 2 * m, h + 2 * m), Image.LANCZOS)


def lcd(im, x0, y0, x1, y1):
    """The green LCD behind live text: a dark bezel, a lit green glass with a faint cell grid and a soft reflection."""
    w, h = x1 - x0, y1 - y0
    S = 2
    lay = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), 8 * S, fill=(10, 14, 16, 255))
    b = 6 * S
    glass = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    gp = glass.load()
    gm = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(gm).rounded_rectangle((b, b, w * S - b, h * S - b), 4 * S, fill=255)
    gmp = gm.load()
    for y in range(h * S):
        for x in range(w * S):
            if gmp[x, y]:
                u, v = x / (w * S), y / (h * S)
                t = 0.35 * v + 0.30 * abs(u - 0.35)
                gp[x, y] = lerp(LCD_HI, LCD_LO, min(1.0, t * 1.4)) + (255,)
    lay.alpha_composite(glass)
    gd = ImageDraw.Draw(lay)
    cell = (w - 12) / 16.0
    for i in range(1, 16):                                    # the cell grid: faint
        x = int((6 + i * cell) * S)
        gd.line((x, b, x, h * S - b), fill=(60, 80, 20, 26), width=1)
    gd.line((b, h * S // 2, w * S - b, h * S // 2), fill=(60, 80, 20, 40), width=1)
    refl = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(refl).polygon([(b, b), (int(w * S * 0.55), b), (int(w * S * 0.30), h * S - b), (b, h * S - b)], fill=(255, 255, 240, 22))
    refl = Image.composite(refl, Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0)), gm)
    lay.alpha_composite(refl)
    ImageDraw.Draw(lay).rounded_rectangle((b, b, w * S - b, h * S - b), 4 * S, outline=(30, 44, 10, 200), width=S)
    lay = lay.resize((w, h), Image.LANCZOS)
    sh = Image.new("RGBA", (w + 16, h + 16), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((8, 11, w + 8, h + 11), 8, fill=SHADOW + (150,))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(4)), (x0 - 8, y0 - 8))
    im.alpha_composite(lay, (x0, y0))


def wordmark(im, x, y):
    """MS2KR in brushed silver with a bevel, and the model line under it"""
    S = 3
    f = ImageFont.truetype(TIT_B, 62 * S)
    t = "MS2KR"
    l, tp, r, b = f.getbbox(t)
    w, h = r - l + 8 * S, b - tp + 8 * S
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((4 * S - l, 4 * S - tp), t, font=f, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = Image.new("RGBA", (w, h), SHADOW + (0,))
    sh.putalpha(mask.filter(ImageFilter.GaussianBlur(2 * S)).point(lambda p: int(p * 0.7)))
    out.alpha_composite(ImageChops.offset(sh, 2 * S, 3 * S))
    grad = Image.new("RGBA", (w, h))
    gp = grad.load()
    for yy in range(h):
        tt = yy / h
        c = lerp((246, 250, 252), (150, 170, 182), tt) if tt > 0.45 else lerp((252, 254, 255), (214, 226, 232), tt / 0.45)
        for xx in range(w):
            gp[xx, yy] = c + (255,)
    fill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fill.paste(grad, (0, 0), mask)
    out.alpha_composite(fill)
    edge = ImageChops.subtract(mask, ImageChops.offset(mask, 0, S * 2))     # light catches the upper edge
    hl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    hl.putalpha(edge.point(lambda p: int(p * 0.8)))
    out.alpha_composite(hl)
    out = out.resize((w // S, h // S), Image.LANCZOS)
    im.alpha_composite(out, (x, y))
    d = ImageDraw.Draw(im)
    d.text((x + 6, y + out.height + 2), "ANALOG MODELING SYNTHESIZER", font=F(13, True), fill=INK_DIM + (255,), anchor="lm")
    return out.size
