"""GOLEO AI botları — "Bugün tutan tahminler" Reels videosu.

Her gün sadece aşağıdaki DATE / BOTS bloğunu güncelle, sonra:
    python3 promo.py                 # edge-tts seslendirmeyle
    python3 promo.py --voice ses.mp3 # kendi tek parça kaydınla (ElevenLabs vb.)
Çıktı: output/goleo_ai_botlar_<tarih>.mp4 (+ _seslendirme.mp3)
"""
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

import audio
import config
import render as R
import tts
from numtr import decimal_to_words, num_to_words
from render import (F_BLACK, F_BOLD, F_XBOLD, GREEN, GREEN_GLOW, GREY, PURPLE, TG_BLUE, WHITE, W, H, FPS,
                    clamp, ease_out_back, ease_out_cubic, emoji_sprite, panel_sprite, place, pop_in, prog,
                    slide_in, text_sprite)

# ============================================================================ GÜNÜN VERİSİ
DATE = "24 KASIM"
DATE_SLUG = "2026-11-24"
BOTS = [
    {"emoji": "🔒", "name": "BANKO BOT", "voice_name": "Banko Bot'tan", "picks": [
        {"home": "Kyoto Sanga", "away": "Pohang Steelers", "score": (1, 0), "pick": "MS 1", "odds": 1.41, "short": "Kyoto"},
        {"home": "Daejeon Citizen", "away": "Beijing Guoan", "score": (3, 2), "pick": "MS 1", "odds": 1.35, "short": "Daejeon"},
        {"home": "Shanghai Port", "away": "Buriram United", "score": (3, 1), "pick": "2.5 ÜST", "odds": 1.38, "short": "Shanghai"},
    ]},
    {"emoji": "🎯", "name": "FAVORİ AVCISI", "voice_name": "Favori Avcısı'ndan", "picks": [
        {"home": "Shanghai Port", "away": "Buriram United", "score": (3, 1), "pick": "MS 1", "odds": 1.65, "short": "Shanghai"},
        {"home": "Al Jabalain", "away": "Al Zulfi", "score": (2, 1), "pick": "MS 1", "odds": 1.61, "short": "Al Jabalain"},
        {"home": "Fratria", "away": "Yantra 1919", "score": (2, 0), "pick": "MS 1", "odds": 1.60, "short": "Fratria"},
    ]},
    {"emoji": "🛡", "name": "KİLİT SAVUNMA", "voice_name": "Kilit Savunma'dan", "picks": [
        {"home": "Chanthaburi", "away": "Esan Pattaya", "score": (2, 0), "pick": "2.5 ALT", "odds": 1.63, "short": "Chanthaburi"},
        {"home": "Orlando Pirates", "away": "Golden Arrows", "score": (2, 0), "pick": "2.5 ALT", "odds": 1.62, "short": "Orlando Pirates"},
    ]},
]
TTS_RATE = 6
OUT_NAME = f"goleo_ai_botlar_{DATE_SLUG}"
# ============================================================================

ALL = [p for b in BOTS for p in b["picks"]]
TOTAL = len(ALL)
AVG_ODDS = round(sum(p["odds"] for p in ALL) / TOTAL, 2)
AUDIO_DIR = "build/promo/audio"


def join_tr(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " ve " + items[-1]


def voice_texts():
    t = {1: f"Bugün GOLEO yapay zekâ botlarında tam {num_to_words(TOTAL)} tahmin tuttu!"}
    for k, b in enumerate(BOTS):
        t[2 + k] = (f"{b['voice_name']} {num_to_words(len(b['picks']))} tutan tahmin: "
                    f"{join_tr([p['short'] for p in b['picks']])}.")
    n = 2 + len(BOTS)
    t[n] = f"Toplamda {num_to_words(TOTAL)} tutan tahmin, ortalama oran {decimal_to_words(AVG_ODDS)}."
    t[n + 1] = ("Yarının tahminleri için Telegram'da Goleo Bot'a gel, "
                "yapay zekâ botları sekmesinden botları takip et!")
    return t


# ----------------------------------------------------------------------------- ses
def synth(rate=TTS_RATE):
    os.makedirs(AUDIO_DIR, exist_ok=True)
    for i, text in voice_texts().items():
        mp3 = f"{AUDIO_DIR}/voice_{i}_raw.mp3"
        words = tts.tts_edge(text, mp3, rate)
        a, words = tts.tighten(tts.decode(mp3), words)
        tts.write_wav(f"{AUDIO_DIR}/voice_{i}.wav", a)
        json.dump({"engine": "edge-tts", "rate": rate, "text": text, "duration": len(a) / tts.SR,
                   "words": words}, open(f"{AUDIO_DIR}/voice_{i}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"[promo] sahne {i}: {len(a) / tts.SR:.2f}s — {text}")


def from_recording(path):
    """Tek parça kendi kaydını align.py mantığıyla sahnelere böler."""
    import align
    align.main(path, texts=voice_texts(), out=AUDIO_DIR, make_ref=synth)


def meta(i):
    return json.load(open(f"{AUDIO_DIR}/voice_{i}.json", encoding="utf-8"))


# ----------------------------------------------------------------------------- ortak çizimler
def overlays(c, t, n, final=False):
    tag = text_sprite(f"GOLEO AI BOTLARI  •  {DATE}", 34, WHITE, F_XBOLD)
    place(c, panel_sprite(tag.width + 50, 70, 35, (30, 18, 56, 220), PURPLE, 3), W / 2, 330)
    place(c, tag, W / 2, 330)
    s18 = text_sprite("18+", 34, GREEN, F_BLACK)
    srest = text_sprite("|  Sorumlu oyna", 32, WHITE, F_BOLD)
    pw = s18.width + srest.width + 40
    place(c, panel_sprite(pw, 62, 31, (10, 6, 20, 200), (90, 70, 130), 2), 50 + pw / 2, 1612)
    place(c, s18, 72 + s18.width / 2, 1612)
    place(c, srest, 76 + s18.width + srest.width / 2, 1612)
    if final:
        g = text_sprite("Geçmiş sonuçlar gelecek için garanti değildir.", 30, GREY, F_BOLD)
        place(c, g, W / 2, 1535)
    if n > 1 and t < 0.2:
        from PIL import Image
        c.alpha_composite(Image.new("RGBA", (W, H), PURPLE + (int(110 * (1 - t / 0.2)),)))


def left(c, spr, x, cy, scale=1.0, alpha=1.0):
    place(c, spr, x + spr.width * scale / 2, cy, scale, alpha)


def pick_card(c, p, cy, t, t0):
    """Maç kartı: takımlar + skor | tercih + oran | ✅ damgası."""
    pr = prog(t, t0, 0.38)
    if pr <= 0:
        return
    e = ease_out_cubic(pr)
    dx = 700 * (1 - e)
    a = clamp(pr * 2.5)
    cw, ch = 960, 218
    x0 = (W - cw) / 2 + dx
    place(c, panel_sprite(cw, ch, 34, (22, 14, 42, 240), (70, 50, 110), 3), W / 2 + dx, cy, 1, a)
    # takımlar ve skorlar
    for k, (team, sc) in enumerate(((p["home"], p["score"][0]), (p["away"], p["score"][1]))):
        y = cy - 46 + k * 92
        win = p["score"][0] > p["score"][1] if k == 0 else p["score"][1] > p["score"][0]
        left(c, text_sprite(team, 46, WHITE if win or p["pick"] != "MS 1" else GREY, F_XBOLD, max_w=470),
             x0 + 34, y, 1, a)
        place(c, text_sprite(str(sc), 58, WHITE, F_BLACK), x0 + 560, y, 1, a)
    # ayraç
    place(c, panel_sprite(4, 170, 2, (70, 50, 110, 255)), x0 + 620, cy, 1, a)
    # tercih + oran
    pk = text_sprite(p["pick"], 40, GREEN, F_BLACK)
    place(c, panel_sprite(max(150, pk.width + 20), 64, 32, (12, 40, 26, 230), GREEN, 3), x0 + 735, cy - 46, 1, a)
    place(c, pk, x0 + 735, cy - 46, 1, a)
    place(c, text_sprite("ORAN", 26, GREY, F_BOLD), x0 + 678, cy + 50, 1, a)
    place(c, text_sprite(f"{p['odds']:.2f}", 50, WHITE, F_BLACK), x0 + 775, cy + 48, 1, a)
    # ✅ damgası
    ps = prog(t, t0 + 0.35, 0.3)
    if ps > 0:
        place(c, emoji_sprite("✅", 84), x0 + cw - 60, cy, 0.4 + 0.6 * ease_out_back(ps, 3.0), clamp(ps * 3))


# ----------------------------------------------------------------------------- sahneler
class Hook(R.Scene):
    def __init__(self, n, m):
        super().__init__(n, m)
        self.t1 = self.ev(0.02, "whoosh")
        self.c0 = self.at("tam", default=0.9)
        self.c1 = self.at("tahmin", default=self.c0 + 0.5) + 0.1
        R.add_ticks(self, self.c0, self.c1, every=3)
        self.t3 = self.ev(self.at("tuttu", default=self.c1) - 0.05, "whoosh")
        self.tchips = self.ev(self.t3 + 0.12, "pop")

    def draw(self, c, t):
        R.slide_in(c, text_sprite("BUGÜN", 110, WHITE), W / 2, 560, t, self.t1, dy=-120)
        p = prog(t, self.c0 - 0.15, 0.3)
        if p > 0:
            v = int(round(TOTAL * ease_out_cubic(prog(t, self.c0, self.c1 - self.c0))))
            land = prog(t, self.c1, 0.3)
            num = text_sprite(str(v), 330, GREEN, glow=GREEN_GLOW, glow_r=30)
            place(c, num, W / 2, 800, (0.4 + 0.6 * ease_out_back(p)) * (1 + 0.12 * math.sin(math.pi * land)),
                  clamp(p * 3))
        row = text_sprite("TAHMİN TUTTU", 84, WHITE, glow=PURPLE, glow_r=18)
        chk = emoji_sprite("✅", 84)
        tw = row.width + 20 + chk.width
        pop_in(c, row, W / 2 - tw / 2 + row.width / 2, 1030, t, self.t3)
        pop_in(c, chk, W / 2 + tw / 2 - chk.width / 2, 1025, t, self.t3 + 0.12)
        for k, b in enumerate(BOTS):
            lab = text_sprite(b["name"], 34, WHITE, F_BLACK)
            em = emoji_sprite(b["emoji"], 38)
            w = lab.width + em.width + 50
            cy = 1200 + k * 82
            pk = prog(t, self.tchips + k * 0.1, 0.3)
            if pk > 0:
                s = 0.4 + 0.6 * ease_out_back(pk)
                place(c, panel_sprite(w, 66, 33, (30, 18, 56, 230), PURPLE, 3), W / 2, cy, s, clamp(pk * 3))
                place(c, em, W / 2 + (-w / 2 + 22 + em.width / 2) * s, cy, s, clamp(pk * 3))
                place(c, lab, W / 2 + (w / 2 - 22 - lab.width / 2) * s, cy, s, clamp(pk * 3))


class BotScene(R.Scene):
    HOLD = 0.8  # kartları okumak için ek süre

    def __init__(self, n, m, bot):
        super().__init__(n, m)
        self.frames += int(round(self.HOLD * FPS))
        self.bot = bot
        self.t_head = self.ev(0.02, "whoosh")
        self.t_cards = []
        prev = 0.35
        for k, p in enumerate(bot["picks"]):
            t = self.at(p["short"].split()[0], default=prev + 0.6) - 0.12
            t = max(t, prev + 0.25)
            self.t_cards.append(t)
            self.ev(t, "whoosh")
            self.ev(t + 0.35, "ding")
            prev = t

    def draw(self, c, t):
        em = emoji_sprite(self.bot["emoji"], 92)
        nm = text_sprite(self.bot["name"], 92, WHITE, glow=PURPLE, glow_r=18)
        tw = em.width + 24 + nm.width
        pop_in(c, em, W / 2 - tw / 2 + em.width / 2, 470, t, self.t_head)
        pop_in(c, nm, W / 2 + tw / 2 - nm.width / 2, 470, t, self.t_head + 0.05)
        cnt = text_sprite(f"{len(self.bot['picks'])} TUTAN TAHMİN", 40, (10, 30, 18), F_BLACK)
        p = prog(t, self.t_head + 0.2, 0.35)
        if p > 0:
            s = 0.4 + 0.6 * ease_out_back(p)
            place(c, panel_sprite(cnt.width + 60, 76, 38, GREEN + (255,), glow=GREEN_GLOW), W / 2, 580, s, clamp(p * 3))
            place(c, cnt, W / 2, 580, s, clamp(p * 3))
        n = len(self.bot["picks"])
        y0 = 800 if n == 3 else 880
        for k, pk in enumerate(self.bot["picks"]):
            pick_card(c, pk, y0 + k * 250, t, self.t_cards[k])


class Recap(R.Scene):
    def __init__(self, n, m):
        super().__init__(n, m)
        self.t1 = self.ev(0.02, "whoosh")
        self.t_bars = self.ev(0.4, "whoosh")
        self.t_avg = self.ev(self.at("ortalama", default=1.6) - 0.05, "pop")
        self.t_odds = self.ev(self.at("oran", default=self.t_avg + 0.4), "ding")

    def draw(self, c, t):
        pop_in(c, text_sprite(f"{TOTAL} TUTAN TAHMİN", 96, GREEN, glow=GREEN_GLOW, glow_r=22, max_w=960),
               W / 2, 470, t, self.t1)
        mx = max(len(b["picks"]) for b in BOTS)
        for k, b in enumerate(BOTS):
            cy = 640 + k * 130
            pb = prog(t, self.t_bars + k * 0.18, 0.5)
            if pb <= 0:
                continue
            a = clamp(pb * 3)
            em = emoji_sprite(b["emoji"], 46)
            place(c, em, 100, cy, 1, a)
            left(c, text_sprite(b["name"], 36, WHITE, F_BLACK), 140, cy - 34, 1, a)
            bw_full = 780
            bw = max(40, int(bw_full * len(b["picks"]) / mx * ease_out_cubic(pb)))
            from PIL import Image, ImageDraw
            bar = Image.new("RGBA", (bw, 34), (0, 0, 0, 0))
            ImageDraw.Draw(bar).rounded_rectangle((0, 0, bw - 1, 33), 17, fill=GREEN + (255,))
            place(c, panel_sprite(bw_full, 34, 17, (36, 24, 60, 255)), 140 + bw_full / 2, cy + 18, 1, a)
            place(c, bar, 140 + bw / 2, cy + 18, 1, a)
            left(c, text_sprite(str(len(b["picks"])), 44, GREEN, F_BLACK), 140 + bw_full + 20, cy + 16, 1, a)
        p = prog(t, self.t_avg, 0.4)
        if p > 0:
            s = 0.4 + 0.6 * ease_out_back(p)
            place(c, R.orb(PURPLE, 300, 0.45), W / 2, 1180, s, clamp(p * 3) * 0.8)
            place(c, panel_sprite(520, 210, 36, (40, 14, 70, 245), PURPLE, 6, glow=PURPLE, glow_r=30),
                  W / 2, 1180, s, clamp(p * 3))
            place(c, text_sprite("ORTALAMA ORAN", 32, GREY, F_BOLD), W / 2, 1115, s, clamp(p * 3))
            pv = prog(t, self.t_odds, 0.3)
            if pv > 0:
                place(c, text_sprite(f"{AVG_ODDS:.2f}", 110, WHITE, glow=GREEN_GLOW, glow_r=16), W / 2, 1205,
                      s * (0.5 + 0.5 * ease_out_back(pv, 3)), clamp(pv * 3))


class CTA(R.Scene):
    def __init__(self, n, m):
        super().__init__(n, m)
        self.t1 = self.ev(0.02, "whoosh")
        self.t_btn = self.ev(self.at("Telegram", default=1.2) - 0.08, "whoosh")
        self.t_user = self.ev(self.at("Goleo", default=1.8), "pop")
        self.t_tab = self.ev(self.at("yapay", default=2.5) - 0.05, "whoosh")

    def draw(self, c, t):
        R.slide_in(c, text_sprite("Yarının tahminleri", 84, WHITE), W / 2, 520, t, self.t1, dy=-90)
        pop_in(c, text_sprite("ÜCRETSİZ", 150, GREEN, glow=GREEN_GLOW, glow_r=26), W / 2, 670, t, self.t1 + 0.15)
        p = prog(t, self.t_btn, 0.42)
        if p > 0:
            since = t - self.t_btn
            base = 0.3 + 0.7 * ease_out_back(p, 2.4)
            pulse = 1 + 0.035 * math.sin(since * 2 * math.pi * 1.5) * clamp(since * 2)
            bw, bh, cy = 880, 170, 900
            ring_p = (since % 0.9) / 0.9
            if since > 0.3:
                place(c, panel_sprite(bw, bh, bh // 2, (0, 0, 0, 0), TG_BLUE, 6), W / 2, cy, 1 + 0.12 * ring_p,
                      (1 - ring_p) * 0.8)
            place(c, panel_sprite(bw, bh, bh // 2, TG_BLUE + (255,), None, glow=TG_BLUE, glow_r=30, glow_a=1.2),
                  W / 2, cy, base * pulse, clamp(p * 3))
            l1 = text_sprite("Telegram'da", 62, WHITE, F_XBOLD)
            l2 = text_sprite(config.BOT_NAME, 66, WHITE, F_BLACK)
            tw = l1.width + 4 + l2.width
            sc = base * pulse
            place(c, l1, W / 2 + (-tw / 2 + l1.width / 2) * sc, cy + 2, sc, clamp(p * 3))
            place(c, l2, W / 2 + (tw / 2 - l2.width / 2) * sc, cy, sc, clamp(p * 3))
        pop_in(c, text_sprite(config.BOT_USERNAME, 74, WHITE, F_BLACK, glow=PURPLE, glow_r=16, glow_a=1.2),
               W / 2, 1085, t, self.t_user)
        p = prog(t, self.t_tab, 0.4)
        if p > 0:
            s = 0.4 + 0.6 * ease_out_back(p)
            em = emoji_sprite("🤖", 54)
            l = text_sprite("AI Botlar sekmesi  →  botları takip et", 40, WHITE, F_XBOLD, max_w=760)
            w = em.width + l.width + 70
            place(c, panel_sprite(w, 96, 48, (30, 18, 56, 235), GREEN, 3), W / 2, 1270, s, clamp(p * 3))
            place(c, em, W / 2 + (-w / 2 + 28 + em.width / 2) * s, 1270, s, clamp(p * 3))
            place(c, l, W / 2 + (w / 2 - 28 - l.width / 2) * s, 1270, s, clamp(p * 3))
        R.slide_in(c, text_sprite("Botları takip et, tahmin tuttuğunda bildirim gelsin", 34, GREY, F_BOLD,
                                  max_w=960), W / 2, 1400, t, self.t_tab + 0.4, dy=40)


def build_scenes():
    sc = [Hook(1, meta(1))]
    for k, b in enumerate(BOTS):
        sc.append(BotScene(2 + k, meta(2 + k), b))
    n = 2 + len(BOTS)
    sc += [Recap(n, meta(n)), CTA(n + 1, meta(n + 1))]
    return sc


def render_scene(i, start, out):
    sc = build_scenes()[i]
    final = i >= len(BOTS) + 1
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", "-profile:v", "high", out], stdin=subprocess.PIPE)
    for f in range(sc.frames):
        t = f / FPS
        c = R.draw_background(start + t)
        sc.draw(c, t)
        overlays(c, t, sc.n, final)
        ff.stdin.write(c.convert("RGB").tobytes())
        if f == sc.frames - 4:
            c.convert("RGB").save(f"build/promo/preview_{sc.n}.png")
    ff.stdin.close()
    if ff.wait():
        sys.exit("render hatası")


def main():
    os.makedirs("build/promo/scenes", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    if "--voice" in sys.argv:
        from_recording(sys.argv[sys.argv.index("--voice") + 1])
    elif "--skip-tts" not in sys.argv:
        synth()
    scenes = build_scenes()
    starts, acc = [], 0
    for s in scenes:
        starts.append(acc / FPS)
        acc += s.frames
    total = acc / FPS
    print(f"[promo] sahneler {[round(s.frames / FPS, 2) for s in scenes]} toplam {total:.2f}s")
    paths = [f"build/promo/scenes/s{i + 1}.mp4" for i in range(len(scenes))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        list(ex.map(render_scene, range(len(scenes)), starts, paths))
    with open("build/promo/scenes/list.txt", "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in paths)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "build/promo/scenes/list.txt",
                    "-c", "copy", "build/promo/video.mp4"], check=True)
    clips = [(st + R.VO, f"{AUDIO_DIR}/voice_{s.n}.wav") for st, s in zip(starts, scenes)]
    events = sorted((st + t, k) for st, s in zip(starts, scenes) for t, k in s.events)
    os.makedirs("build/promo/mix", exist_ok=True)
    mix_wav, voice_wav = audio.mix(total, clips, events, "build/promo/mix")
    out = f"output/{OUT_NAME}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "build/promo/video.mp4", "-i", mix_wav, "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                    "-t", f"{total:.3f}", "-movflags", "+faststart", out], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", voice_wav, "-c:a", "libmp3lame", "-b:a", "192k",
                    f"output/{OUT_NAME}_seslendirme.mp3"], check=True)
    m = audio.measure(out)
    print(f"[promo] {out}  {m['input_i']} LUFS / {m['input_tp']} dBTP")


if __name__ == "__main__":
    main()
