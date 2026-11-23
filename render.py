"""Sahneleri kare kare çizip her birini ayrı mp4 olarak render eder (Pillow -> ffmpeg).

Animasyonlar seslendirmedeki kelime zamanlarına (build/audio/voice_N.json) göre
zamanlanır. Ses efekti olayları (whoosh / tick / ding) build/sfx_events.json'a yazılır.
"""
import json
import math
import os
import subprocess
import sys
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

W, H, FPS = 1080, 1920, 30
VO = 0.10                # seslendirme sahne başından bu kadar sonra başlar
SAFE_TOP, SAFE_BOTTOM = 250, H - 250

# Renkler
BG_TOP = (14, 8, 28)
BG_BOT = (6, 4, 14)
GREEN = (57, 255, 136)
GREEN_GLOW = (0, 190, 90)
PURPLE = (176, 76, 255)
PURPLE_D = (110, 40, 190)
WHITE = (255, 255, 255)
GREY = (190, 182, 210)
TG_BLUE = (34, 158, 217)
CARD = (24, 16, 44)

FONT_DIR = "/usr/share/fonts/opentype/inter"
F_BLACK = os.path.join(FONT_DIR, "Inter-Black.otf")
F_XBOLD = os.path.join(FONT_DIR, "Inter-ExtraBold.otf")
F_BOLD = os.path.join(FONT_DIR, "Inter-Bold.otf")
F_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"


# ----------------------------------------------------------------------------- yardımcılar
@lru_cache(None)
def font(path, size):
    return ImageFont.truetype(path, size)


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out_cubic(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_out_back(x, s=2.2):
    x = clamp(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def prog(t, t0, dur):
    return clamp((t - t0) / dur)


def alpha_lut(a):
    return [int(i * a) for i in range(256)]


def place(canvas, spr, cx, cy, scale=1.0, alpha=1.0):
    if alpha <= 0.01 or scale <= 0.01:
        return
    if abs(scale - 1) > 0.004:
        spr = spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))),
                         Image.BILINEAR)
    if alpha < 0.995:
        spr = spr.copy()
        spr.putalpha(spr.getchannel("A").point(alpha_lut(alpha)))
    x = int(round(cx - spr.width / 2))
    y = int(round(cy - spr.height / 2))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + spr.width), min(H, y + spr.height)
    if x1 <= x0 or y1 <= y0:
        return
    if (x0, y0, x1, y1) != (x, y, x + spr.width, y + spr.height):
        spr = spr.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    canvas.alpha_composite(spr, (x0, y0))


def glowify(mask, color, glow, glow_r, glow_a, pad):
    """mask (L) -> RGBA: renkli dolgu + isteğe bağlı neon parıltı."""
    w, h = mask.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if glow:
        g = mask.filter(ImageFilter.GaussianBlur(glow_r))
        g = g.point([min(255, int(v * glow_a)) for v in range(256)])
        layer = Image.new("RGBA", (w, h), glow + (0,))
        layer.putalpha(g)
        out.alpha_composite(layer)
        g2 = mask.filter(ImageFilter.GaussianBlur(max(2, glow_r // 4)))
        layer2 = Image.new("RGBA", (w, h), glow + (0,))
        layer2.putalpha(g2.point([min(255, int(v * 0.4)) for v in range(256)]))
        out.alpha_composite(layer2)
    txt = Image.new("RGBA", (w, h), color + (0,))
    txt.putalpha(mask)
    out.alpha_composite(txt)
    return out


@lru_cache(maxsize=512)
def text_sprite(text, size, color=WHITE, fpath=F_BLACK, glow=None, glow_r=22, glow_a=1.1,
                max_w=None):
    f = font(fpath, size)
    if max_w:
        while f.getlength(text) > max_w and size > 20:
            size -= 2
            f = font(fpath, size)
    bb = f.getbbox(text)
    pad = glow_r * 3 if glow else 6
    w, h = bb[2] - bb[0] + 2 * pad, bb[3] - bb[1] + 2 * pad
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad - bb[0], pad - bb[1]), text, font=f, fill=255)
    return glowify(mask, color, glow, glow_r, glow_a, pad)


@lru_cache(None)
def emoji_sprite(ch, size):
    f = font(F_EMOJI, 109)
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox())
    return im.resize((int(im.width * size / im.height), size), Image.LANCZOS)


@lru_cache(None)
def panel_sprite(w, h, r, fill, border=None, bw=4, glow=None, glow_r=26, glow_a=1.3):
    pad = glow_r * 3 if glow else 4
    W2, H2 = w + 2 * pad, h + 2 * pad
    out = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    box = (pad, pad, pad + w, pad + h)
    if glow:
        m = Image.new("L", (W2, H2), 0)
        ImageDraw.Draw(m).rounded_rectangle(box, r, outline=255, width=bw * 3)
        g = m.filter(ImageFilter.GaussianBlur(glow_r)).point(
            [min(255, int(v * glow_a)) for v in range(256)])
        layer = Image.new("RGBA", (W2, H2), glow + (0,))
        layer.putalpha(g)
        out.alpha_composite(layer)
    d = ImageDraw.Draw(out)
    d.rounded_rectangle(box, r, fill=fill, outline=border, width=bw if border else 0)
    return out


@lru_cache(None)
def arrow_down_sprite(size, color, glow):
    pad = 60
    m = Image.new("L", (size + 2 * pad, size + 2 * pad), 0)
    d = ImageDraw.Draw(m)
    s = size
    sw = s * 0.26
    cx = pad + s / 2
    d.rectangle((cx - sw / 2, pad, cx + sw / 2, pad + s * 0.55), fill=255)
    d.polygon([(pad, pad + s * 0.45), (pad + s, pad + s * 0.45), (cx, pad + s)], fill=255)
    return glowify(m, color, glow, 20, 1.6, pad)


# ----------------------------------------------------------------------------- arka plan
@lru_cache(None)
def bg_base():
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        k = y / H
        c = tuple(int(BG_TOP[i] * (1 - k) + BG_BOT[i] * k) for i in range(3))
        d.line((0, y, W, y), fill=c)
    return im.convert("RGBA")


@lru_cache(None)
def orb(color, radius, strength):
    size = radius * 2
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse((radius * 0.35, radius * 0.35, size - radius * 0.35,
                               size - radius * 0.35), fill=int(255 * strength))
    m = m.filter(ImageFilter.GaussianBlur(radius * 0.32))
    im = Image.new("RGBA", (size, size), color + (0,))
    im.putalpha(m)
    return im


GRID = 90


@lru_cache(None)
def grid_layer():
    im = Image.new("RGBA", (W, H + GRID), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in range(0, W + 1, GRID):
        d.line((x, 0, x, H + GRID), fill=PURPLE + (18,), width=2)
    for y in range(0, H + GRID + 1, GRID):
        d.line((0, y, W, y), fill=PURPLE + (18,), width=2)
    return im


def draw_background(gt):
    """gt = videonun genel zamanı (sahneler arası kesintisiz hareket için)."""
    c = bg_base().copy()
    off = int((gt * 35) % GRID)
    c.alpha_composite(grid_layer().crop((0, off, W, off + H)))
    place(c, orb(PURPLE, 520, 0.42), 860 + 90 * math.sin(gt * 0.6), 420 + 80 * math.cos(gt * 0.5))
    place(c, orb(GREEN, 440, 0.20), 180 + 80 * math.cos(gt * 0.7), 1500 + 90 * math.sin(gt * 0.4))
    place(c, orb(PURPLE_D, 380, 0.30), 200 + 60 * math.sin(gt * 0.9), 900 + 70 * math.cos(gt * 0.8))
    # yükselen küçük parçacıklar
    d = ImageDraw.Draw(c)
    for i in range(22):
        px = (i * 197 + 53) % W
        py = (H - ((gt * (40 + (i % 5) * 18) + i * 311) % (H + 40)))
        r = 2 + (i % 3)
        col = GREEN if i % 3 == 0 else PURPLE
        d.ellipse((px - r, py - r, px + r, py + r), fill=col + (90,))
    return c


def draw_overlays(c, t, scene_no):
    # Üst seri etiketi
    tag = text_sprite(f"{config.fmt_tl(config.START_BANKROLL)} TL'DEN GTA 6'YA  •  BÖLÜM {config.STEP}",
                      34, WHITE, F_XBOLD)
    pw = tag.width + 50
    place(c, panel_sprite(pw, 70, 35, (30, 18, 56, 220), PURPLE, 3), W / 2, 330)
    place(c, tag, W / 2, 330)
    # 18+ uyarısı (alt sol, güvenli alanın içinde)
    s18 = text_sprite("18+", 34, GREEN, F_BLACK)
    srest = text_sprite("|  Sorumlu oyna", 32, WHITE, F_BOLD)
    pw = s18.width + srest.width + 40
    x0 = 50
    place(c, panel_sprite(pw, 62, 31, (10, 6, 20, 200), (90, 70, 130), 2), x0 + pw / 2, 1612)
    place(c, s18, x0 + 22 + s18.width / 2, 1612)
    place(c, srest, x0 + 22 + s18.width + 4 + srest.width / 2, 1612)
    # sahne başında kısa flaş
    if scene_no > 1 and t < 0.2:
        a = int(110 * (1 - t / 0.2))
        c.alpha_composite(Image.new("RGBA", (W, H), PURPLE + (a,)))


# ----------------------------------------------------------------------------- animasyon kalıpları
def pop_in(c, spr, cx, cy, t, t0, dur=0.38, base=1.0):
    p = prog(t, t0, dur)
    if p <= 0:
        return
    place(c, spr, cx, cy, base * (0.35 + 0.65 * ease_out_back(p)), clamp(p * 2.5))


def slide_in(c, spr, cx, cy, t, t0, dx=0, dy=0, dur=0.35):
    p = prog(t, t0, dur)
    if p <= 0:
        return
    e = ease_out_cubic(p)
    place(c, spr, cx + dx * (1 - e), cy + dy * (1 - e), 1.0, clamp(p * 2))


class Scene:
    def __init__(self, n, meta):
        self.n = n
        self.meta = meta
        self.dur = meta["duration"] + config.SCENE_PAD
        self.frames = int(round(self.dur * FPS))
        self.events = []  # (sahne_içi_zaman, tür)

    def at(self, prefix, nth=0, default=0.0):
        """Seste `prefix` ile başlayan kelimenin başlama zamanı (sahne zamanı)."""
        hits = [w for w in self.meta["words"] if w["word"].lower().startswith(prefix.lower())]
        if len(hits) > nth:
            return VO + hits[nth]["start"]
        return default

    def after(self, t, default):
        """t'den sonra başlayan ilk kelimenin zamanı."""
        for w in self.meta["words"]:
            if VO + w["start"] > t:
                return VO + w["start"]
        return default

    def ev(self, t, kind):
        self.events.append((round(t, 3), kind))
        return t


# ----------------------------------------------------------------------------- SAHNE 1: HOOK
class Hook(Scene):
    def __init__(self, n, meta):
        super().__init__(n, meta)
        self.t_a = self.ev(0.02, "whoosh")
        self.t_arrow = self.ev(self.at("liradan", default=0.4) + 0.1, "pop")
        self.t_b = self.ev(self.at("GTA", default=0.8) - 0.05, "whoosh")
        self.t_step = self.ev(self.at("Birinci", default=1.8) - 0.05, "pop")

    def draw(self, c, t):
        a = text_sprite(f"{config.fmt_tl(config.START_BANKROLL)} TL", 200, GREEN, glow=GREEN_GLOW)
        slide_in(c, a, W / 2, 680, t, self.t_a, dx=-700, dur=0.3)
        ar = arrow_down_sprite(120, PURPLE, PURPLE)
        p = prog(t, self.t_arrow, 0.3)
        if p > 0:
            bob = 10 * math.sin((t - self.t_arrow) * 7)
            place(c, ar, W / 2, 900 + bob, 0.4 + 0.6 * ease_out_back(p), clamp(p * 3))
        b = text_sprite("GTA 6", 250, WHITE, glow=PURPLE, glow_r=30, glow_a=2.0)
        p = prog(t, self.t_b, 0.42)
        if p > 0:
            pulse = 1 + 0.025 * math.sin((t - self.t_b) * 9) * (p >= 1)
            place(c, b, W / 2, 1120, (0.2 + 0.8 * ease_out_back(p, 2.6)) * pulse, clamp(p * 3))
        # "1. ADIM" rozeti
        lab = text_sprite(f"{config.STEP}. ADIM", 76, WHITE)
        pw = lab.width + 90
        p = prog(t, self.t_step, 0.38)
        if p > 0:
            s = 0.3 + 0.7 * ease_out_back(p)
            place(c, panel_sprite(pw, 130, 65, PURPLE + (255,), None, glow=PURPLE), W / 2, 1360, s, clamp(p * 3))
            place(c, lab, W / 2, 1360, s, clamp(p * 3))


# ----------------------------------------------------------------------------- SAHNE 2: KASA
class Kasa(Scene):
    def __init__(self, n, meta):
        super().__init__(n, meta)
        self.t_lab = self.ev(0.02, "whoosh")
        self.t_card = self.ev(0.18, "whoosh")
        self.c0 = self.at("kasa", default=0.5)
        self.c1 = max(self.c0 + 0.6, self.at("lira", default=1.3) + 0.15)
        add_ticks(self, self.c0, self.c1)

    def draw(self, c, t):
        lab = text_sprite("BAŞLANGIÇ KASASI", 80, WHITE, glow=PURPLE, glow_r=16, glow_a=1.0, max_w=940)
        slide_in(c, lab, W / 2, 700, t, self.t_lab, dy=-120)
        p = prog(t, self.t_card, 0.4)
        if p > 0:
            s = 0.6 + 0.4 * ease_out_back(p)
            place(c, panel_sprite(900, 330, 48, CARD + (235,), GREEN, 5, glow=GREEN_GLOW), W / 2, 960, s, clamp(p * 3))
            v = counter_value(t, self.c0, self.c1, 0, config.BANKROLL)
            num = text_sprite(f"{config.fmt_tl(v)} TL", 180, GREEN, glow=GREEN_GLOW, glow_r=18, max_w=820)
            land = prog(t, self.c1, 0.25)
            bump = 1 + 0.08 * math.sin(math.pi * land)
            place(c, num, W / 2, 960, s * bump, clamp(p * 3))
        goal = text_sprite("HEDEF  →  GTA 6", 54, PURPLE, F_BLACK, glow=PURPLE, glow_r=12, glow_a=0.9)
        slide_in(c, goal, W / 2, 1220, t, self.c1, dy=60)


def counter_value(t, t0, t1, a, b):
    return a + (b - a) * ease_out_cubic(prog(t, t0, t1 - t0))


def add_ticks(scene, t0, t1, every=2):
    n = int((t1 - t0) * FPS)
    for k in range(0, n, every):
        scene.ev(t0 + k / FPS, "tick")
    scene.ev(t1, "ding")


# ----------------------------------------------------------------------------- SAHNE 3: TERCİH
class Tercih(Scene):
    def __init__(self, n, meta):
        super().__init__(n, meta)
        self.t_head = self.ev(0.02, "whoosh")
        self.t_card = self.ev(self.at("tercih", default=0.4), "whoosh")
        self.t_home = self.ev(self.at(config.HOME_TEAM[:4], default=1.0) - 0.05, "pop")
        self.t_away = self.ev(self.at(config.AWAY_TEAM[:4], default=1.9) - 0.05, "pop")
        first_pick_word = config.PICK_SPOKEN.split()[0]
        self.t_pick = self.ev(self.at(first_pick_word, default=2.8) - 0.05, "whoosh")
        self.t_odds = self.ev(self.at("Oran", default=4.7) - 0.05, "whoosh")
        self.t_odds_val = self.ev(self.after(self.t_odds + 0.06, default=self.t_odds + 0.5) - 0.05, "ding")

    def draw(self, c, t):
        head = text_sprite("GÜNÜN TERCİHİ", 92, GREEN, glow=GREEN_GLOW, glow_r=20)
        pop_in(c, head, W / 2, 470, t, self.t_head)
        # maç kartı
        p = prog(t, self.t_card, 0.42)
        if p > 0:
            e = ease_out_cubic(p)
            cy = 820 + 260 * (1 - e)
            a = clamp(p * 2.5)
            place(c, panel_sprite(940, 440, 44, CARD + (240,), PURPLE, 4, glow=PURPLE, glow_a=0.9), W / 2, cy, 1, a)
            mac = text_sprite("MAÇ", 34, GREY, F_BOLD)
            place(c, mac, W / 2, cy - 175, 1, a)
            home = text_sprite(config.HOME_TEAM.upper(), 92, WHITE, max_w=820)
            away = text_sprite(config.AWAY_TEAM.upper(), 92, WHITE, max_w=820)
            ph = prog(t, self.t_home, 0.32)
            if ph > 0:
                place(c, home, W / 2 - 500 * (1 - ease_out_cubic(ph)), cy - 95, 1, clamp(ph * 2) * a)
            vs = panel_sprite(120, 76, 38, PURPLE + (255,))
            pv = prog(t, (self.t_home + self.t_away) / 2, 0.3)
            if pv > 0:
                s = 0.3 + 0.7 * ease_out_back(pv)
                place(c, vs, W / 2, cy + 15, s, a)
                place(c, text_sprite("VS", 44, WHITE), W / 2, cy + 15, s, a)
            pa = prog(t, self.t_away, 0.32)
            if pa > 0:
                place(c, away, W / 2 + 500 * (1 - ease_out_cubic(pa)), cy + 125, 1, clamp(pa * 2) * a)
        # tercih
        p = prog(t, self.t_pick, 0.4)
        if p > 0:
            s = 0.4 + 0.6 * ease_out_back(p)
            pick = text_sprite(config.PICK, 76, GREEN, glow=GREEN_GLOW, glow_r=14, glow_a=1.1, max_w=860)
            place(c, panel_sprite(max(pick.width - 40, 700), 140, 70, (12, 40, 26, 230), GREEN, 4),
                  W / 2, 1185, s, clamp(p * 3))
            place(c, text_sprite("TERCİH", 30, GREY, F_BOLD), W / 2, 1090, s, clamp(p * 3))
            place(c, pick, W / 2, 1190, s, clamp(p * 3))
        # oran kutusu (parlayarak)
        p = prog(t, self.t_odds, 0.45)
        if p > 0:
            s = 0.3 + 0.7 * ease_out_back(p, 2.8)
            a = clamp(p * 3)
            since = max(0.0, t - self.t_odds)
            glow_pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(since * 8))
            box = panel_sprite(420, 200, 36, (40, 14, 70, 245), PURPLE, 6, glow=PURPLE, glow_r=34, glow_a=1.6)
            halo = orb(PURPLE, 330, 0.55)
            place(c, halo, W / 2, 1410, s * (0.9 + 0.15 * glow_pulse), a * glow_pulse)
            place(c, box, W / 2, 1410, s, a)
            place(c, text_sprite("ORAN", 30, GREY, F_BOLD), W / 2, 1345, s, a)
            pv = prog(t, self.t_odds_val, 0.3)
            if pv > 0:
                val = text_sprite(config.fmt_odds(config.ODDS), 120, WHITE, glow=GREEN_GLOW, glow_r=18)
                place(c, val, W / 2, 1430, s * (0.5 + 0.5 * ease_out_back(pv, 3.0)), a * clamp(pv * 3))
            # parlama süpürmesi
            sw = prog(t, self.t_odds + 0.35, 0.55)
            if 0 < sw < 1:
                shine(c, W / 2, 1410, 420, 200, sw)


def shine(c, cx, cy, w, h, p):
    band = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(band)
    x = -120 + (w + 240) * p
    d.polygon([(x, 0), (x + 70, 0), (x - 10, h), (x - 80, h)], fill=120)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), 36, fill=255)
    from PIL import ImageChops
    band = ImageChops.multiply(band, mask).filter(ImageFilter.GaussianBlur(6))
    im = Image.new("RGBA", (w, h), WHITE + (0,))
    im.putalpha(band)
    place(c, im, cx, cy)


# ----------------------------------------------------------------------------- SAHNE 4: HESAP
class Hesap(Scene):
    def __init__(self, n, meta):
        super().__init__(n, meta)
        self.t_eq = self.ev(0.02, "whoosh")
        self.c0 = self.at("kasa", default=0.4)
        self.c1 = max(self.c0 + 0.8, self.at("çıkıyor", default=1.6) + 0.05)
        add_ticks(self, self.c0, self.c1)
        self.t_bar = self.ev(0.25, "whoosh")
        from numtr import ordinal_words
        self.t_next = self.ev(self.at(ordinal_words(config.NEXT_STEP).split()[0], default=2.4) - 0.05,
                              "whoosh")

    def draw(self, c, t):
        head = text_sprite("HESAP", 60, PURPLE, glow=PURPLE, glow_r=14, glow_a=1.1)
        pop_in(c, head, W / 2, 470, t, self.t_eq)
        eq = text_sprite(f"{config.fmt_tl(config.BANKROLL)} TL × {config.fmt_odds(config.ODDS)} =",
                         96, WHITE, max_w=960)
        slide_in(c, eq, W / 2, 620, t, self.t_eq, dx=600, dur=0.3)
        v = counter_value(t, self.c0, self.c1, config.BANKROLL, config.NEW_BANKROLL)
        num = text_sprite(f"{config.fmt_tl(v)} TL", 200, GREEN, glow=GREEN_GLOW, glow_r=24, max_w=960)
        land = prog(t, self.c1, 0.28)
        p = prog(t, 0.12, 0.35)
        if p > 0:
            place(c, num, W / 2, 820, (0.5 + 0.5 * ease_out_back(p)) * (1 + 0.1 * math.sin(math.pi * land)),
                  clamp(p * 3))
        # GTA 6 hedef çubuğu
        p = prog(t, self.t_bar, 0.4)
        if p > 0:
            a = clamp(p * 2.5)
            dy = 80 * (1 - ease_out_cubic(p))
            frac0 = config.BANKROLL / config.GOAL_TL
            frac1 = config.NEW_BANKROLL / config.GOAL_TL
            fill_p = ease_out_cubic(prog(t, self.c0, self.c1 - self.c0))
            frac = min(1.0, frac0 + (frac1 - frac0) * fill_p)
            if t < self.c0:
                frac = frac0 * ease_out_cubic(prog(t, self.t_bar, 0.5))
            progress_bar(c, 1110 + dy, frac, a)
        # alt satır
        line1 = text_sprite(f"Tutarsa {config.NEXT_STEP}. adımda", 58, WHITE, F_XBOLD)
        line2 = text_sprite(f"{config.fmt_tl(config.NEW_BANKROLL)} TL ile devam", 58, GREEN, F_BLACK,
                            glow=GREEN_GLOW, glow_r=10, glow_a=0.8)
        fire = emoji_sprite("🔥", 64)
        p = prog(t, self.t_next, 0.38)
        if p > 0:
            pop_in(c, line1, W / 2, 1330, t, self.t_next)
            lw = line2.width + 14 + fire.width
            pop_in(c, line2, W / 2 - lw / 2 + line2.width / 2, 1410, t, self.t_next + 0.08)
            pf = prog(t, self.t_next + 0.2, 0.35)
            if pf > 0:
                wob = 1 + 0.08 * math.sin((t - self.t_next) * 12)
                place(c, fire, W / 2 + lw / 2 - fire.width / 2, 1405, (0.3 + 0.7 * ease_out_back(pf)) * wob,
                      clamp(pf * 3))


def progress_bar(c, cy, frac, a):
    bw, bh = 880, 46
    x0 = (W - bw) / 2
    lab = text_sprite("GTA 6 HEDEFİ", 40, WHITE, F_BLACK)
    pct = text_sprite(f"%{int(round(frac * 100))}", 40, GREEN, F_BLACK)
    place(c, lab, x0 + lab.width / 2 - 6, cy - 62, 1, a)
    place(c, pct, x0 + bw - pct.width / 2 + 6, cy - 62, 1, a)
    goal = text_sprite(f"{config.fmt_tl(config.GOAL_TL)} TL", 30, GREY, F_BOLD)
    place(c, goal, x0 + bw - goal.width / 2 + 4, cy + 58, 1, a)
    place(c, panel_sprite(bw, bh, bh // 2, (36, 24, 60, 255), (90, 60, 140), 3), W / 2, cy, 1, a)
    fw = max(bh, int(bw * frac))
    pad = 40
    im = Image.new("RGBA", (fw + 2 * pad, bh + 2 * pad), (0, 0, 0, 0))
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((pad, pad, pad + fw, pad + bh), bh // 2, fill=255)
    g = m.filter(ImageFilter.GaussianBlur(16))
    gl = Image.new("RGBA", im.size, GREEN + (0,))
    gl.putalpha(g)
    im.alpha_composite(gl)
    grad = Image.new("RGBA", im.size)
    gd = ImageDraw.Draw(grad)
    for x in range(im.width):
        k = clamp((x - pad) / max(1, fw))
        col = tuple(int(GREEN[i] * (1 - k) + PURPLE[i] * k) for i in range(3))
        gd.line((x, 0, x, im.height), fill=col + (255,))
    grad.putalpha(m)
    im.alpha_composite(grad)
    if a < 0.995:
        im.putalpha(im.getchannel("A").point(alpha_lut(a)))
    c.alpha_composite(im, (int(x0 - pad), int(cy - bh / 2 - pad)))


# ----------------------------------------------------------------------------- SAHNE 5: CTA
class CTA(Scene):
    def __init__(self, n, meta):
        super().__init__(n, meta)
        self.t_l1 = self.ev(0.02, "whoosh")
        self.t_free = self.ev(self.at("ücretsiz", default=0.5) - 0.05, "pop")
        self.t_l3 = self.at("tercih", default=1.0) - 0.05
        self.t_btn = self.ev(self.at("Telegram", default=1.7) - 0.08, "whoosh")
        self.t_user = self.ev(self.at("Goleo", default=2.3), "pop")
        self.t_foot = self.ev(self.at("Takip", default=3.2) - 0.05, "whoosh")

    def draw(self, c, t):
        slide_in(c, text_sprite("Daha fazla", 84, WHITE), W / 2, 540, t, self.t_l1, dy=-90)
        pop_in(c, text_sprite("ÜCRETSİZ", 170, GREEN, glow=GREEN_GLOW, glow_r=26), W / 2, 690, t, self.t_free, 0.42)
        slide_in(c, text_sprite("tercih için", 84, WHITE), W / 2, 845, t, self.t_l3, dy=90)
        # Telegram butonu
        p = prog(t, self.t_btn, 0.42)
        if p > 0:
            since = t - self.t_btn
            base = 0.3 + 0.7 * ease_out_back(p, 2.4)
            pulse = 1 + 0.035 * math.sin(since * 2 * math.pi * 1.5) * clamp(since * 2)
            bw, bh = 880, 170
            # nabız halkası
            ring_p = (since % 0.9) / 0.9
            if since > 0.3:
                ring = panel_sprite(bw, bh, bh // 2, (0, 0, 0, 0), TG_BLUE, 6)
                place(c, ring, W / 2, 1070, 1 + 0.12 * ring_p, (1 - ring_p) * 0.8)
            btn = panel_sprite(bw, bh, bh // 2, TG_BLUE + (255,), None, glow=TG_BLUE, glow_r=30, glow_a=1.2)
            place(c, btn, W / 2, 1070, base * pulse, clamp(p * 3))
            lbl1 = text_sprite("Telegram'da", 62, WHITE, F_XBOLD)
            lbl2 = text_sprite(config.BOT_NAME, 66, WHITE, F_BLACK)
            gap = 4
            tw = lbl1.width + gap + lbl2.width
            sc = base * pulse
            place(c, lbl1, W / 2 + (-tw / 2 + lbl1.width / 2) * sc, 1072, sc, clamp(p * 3))
            place(c, lbl2, W / 2 + (tw / 2 - lbl2.width / 2) * sc, 1070, sc, clamp(p * 3))
        user = text_sprite(config.BOT_USERNAME, 74, WHITE, F_BLACK, glow=PURPLE, glow_r=16, glow_a=1.2,
                           max_w=940)
        pop_in(c, user, W / 2, 1255, t, self.t_user)
        foot = text_sprite(f"Takip et, seri devam ediyor — {config.BRAND}", 40, GREY, F_BOLD, max_w=960)
        slide_in(c, foot, W / 2, 1450, t, self.t_foot, dy=50)


SCENES = [Hook, Kasa, Tercih, Hesap, CTA]


def load_meta(i):
    with open(os.path.join("build", "audio", f"voice_{i}.json"), encoding="utf-8") as f:
        return json.load(f)


def build_scenes():
    return [cls(i + 1, load_meta(i + 1)) for i, cls in enumerate(SCENES)]


def render_scene(i, start_time, out_path, preview_dir=None):
    sc = build_scenes()[i]
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                           "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                           "-profile:v", "high", "-r", str(FPS), out_path], stdin=subprocess.PIPE)
    for f in range(sc.frames):
        t = f / FPS
        c = draw_background(start_time + t)
        sc.draw(c, t)
        draw_overlays(c, t, sc.n)
        ff.stdin.write(c.convert("RGB").tobytes())
        if preview_dir and f == sc.frames - 4:
            c.convert("RGB").save(os.path.join(preview_dir, f"scene{sc.n}.png"))
    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit(f"ffmpeg sahne {sc.n} render hatası")
    return out_path


if __name__ == "__main__":
    # tek sahne önizleme: python3 render.py 3
    scenes = build_scenes()
    i = int(sys.argv[1]) - 1
    os.makedirs("build/scenes", exist_ok=True)
    os.makedirs("build/preview", exist_ok=True)
    start = sum(s.frames for s in scenes[:i]) / FPS
    render_scene(i, start, f"build/scenes/scene{i + 1}.mp4", "build/preview")
