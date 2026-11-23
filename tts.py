"""Her sahnenin seslendirmesini ayrı dosya olarak üretir + kelime zamanlarını kaydeder.

Sıra: edge-tts (tr-TR-AhmetNeural) -> gTTS (tr) -> Piper (tr_TR-dfki-medium).
Çıktı: build/audio/voice_N.wav + build/audio/voice_N.json  (süre + kelime zamanları)
"""
import asyncio
import json
import os
import subprocess
import sys

import numpy as np

import config

OUT = os.path.join("build", "audio")
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


SR = 48000
MAX_PAUSE = 0.22   # cümle arası uzun duraklamalar bu süreye kısaltılır (sn)


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def write_wav(path, a):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1",
                    "-i", "-", path], input=a.astype(np.float32).tobytes(), check=True)


def tighten(a, words):
    """Baş/son sessizliği kırpar, MAX_PAUSE'dan uzun duraklamaları kısaltır.
    Kelime zamanlarını da aynı şekilde kaydırır. (yeni_ses, yeni_kelimeler)"""
    hop = int(SR * 0.01)
    n = len(a) // hop
    rms = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1))
    loud = 20 * np.log10(rms + 1e-9) > -45
    idx = np.flatnonzero(loud)
    first, last = idx[0], idx[-1] + 1
    # sessiz bölgeleri bul (kare cinsinden)
    cuts = []  # (başlangıç_sn, çıkarılan_sn)
    i = first
    while i < last:
        if not loud[i]:
            j = i
            while j < last and not loud[j]:
                j += 1
            dur = (j - i) * 0.01
            if dur > MAX_PAUSE:
                cuts.append((i, j))
            i = j
        else:
            i += 1
    keep = np.zeros(n, bool)
    keep[max(0, first - 2): min(n, last + 3)] = True
    removed = []
    for (i, j) in cuts:
        excess = int(round((j - i) - MAX_PAUSE * 100))
        mid = (i + j) // 2
        keep[mid - excess // 2: mid - excess // 2 + excess] = False
        removed.append((i * 0.01, excess * 0.01))
    lead = max(0, first - 2) * 0.01
    # kısa crossfade'li birleştirme
    segs, k = [], 0
    while k < n:
        if keep[k]:
            m = k
            while m < n and keep[m]:
                m += 1
            seg = a[k * hop: m * hop].copy()
            f = min(len(seg) // 2, int(SR * 0.008))
            if f:
                seg[:f] *= np.linspace(0, 1, f)
                seg[-f:] *= np.linspace(1, 0, f)
            segs.append(seg)
            k = m
        else:
            k += 1
    out = np.concatenate(segs)

    def shift(t):
        t2 = t - lead
        for (ts, ex) in removed:
            if t > ts:
                t2 -= ex
        return max(0.0, t2)

    words = [{**w, "start": shift(w["start"]), "end": shift(w["end"])} for w in words]
    return out, words


async def _edge(text, mp3, rate):
    import edge_tts
    com = edge_tts.Communicate(text, config.TTS_VOICE, rate=f"{rate:+d}%",
                               boundary="WordBoundary", proxy=PROXY)
    words = []
    with open(mp3, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"word": chunk["text"],
                              "start": chunk["offset"] / 1e7,
                              "end": (chunk["offset"] + chunk["duration"]) / 1e7})
    return words


def tts_edge(text, mp3, rate):
    return asyncio.run(_edge(text, mp3, rate))


def _speedup(mp3, rate):
    """gTTS/Piper hız ayarı vermez: hızı ffmpeg atempo ile uygula."""
    if rate:
        tmp = mp3[:-4] + "_tmp.mp3"
        os.replace(mp3, tmp)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-af",
                        f"atempo={1 + rate / 100:.3f}", mp3], check=True)


def tts_gtts(text, mp3, rate):
    from gtts import gTTS
    gTTS(text, lang="tr").save(mp3)
    _speedup(mp3, rate)
    return []


def tts_piper(text, mp3, rate):
    model = os.environ.get("PIPER_MODEL", "models/tr_TR-dfki-medium.onnx")
    wav = mp3[:-4] + "_piper.wav"
    subprocess.run(["piper", "--model", model, "--output_file", wav],
                   input=text, text=True, check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, mp3], check=True)
    _speedup(mp3, rate)
    return []


ENGINES = [("edge-tts", tts_edge), ("gTTS", tts_gtts), ("piper", tts_piper)]


def estimate_words(text, dur):
    """Kelime zamanı vermeyen motorlar için harf sayısına göre tahmin."""
    toks = text.split()
    total = sum(len(t) for t in toks) or 1
    t, out = 0.0, []
    for tok in toks:
        d = dur * len(tok) / total
        out.append({"word": tok.strip(".,!?:"), "start": t, "end": t + d})
        t += d
    return out


def synth_all(rate, engine=None):
    texts = config.voice_texts()
    used, metas = engine, {}
    for i, text in texts.items():
        mp3 = os.path.join(OUT, f"voice_{i}_raw.mp3")
        words = None
        for name, fn in ENGINES:
            if used and name != used:
                continue  # tüm sahnelerde aynı motoru kullan
            try:
                words = fn(text, mp3, rate)
                if os.path.getsize(mp3) < 1000:
                    raise RuntimeError("boş ses dosyası")
                used = name
                break
            except Exception as e:  # noqa: BLE001
                print(f"[tts] {name} başarısız: {e}", file=sys.stderr)
        if words is None:
            sys.exit("Hiçbir TTS motoru çalışmadı.")
        raw = decode(mp3)
        if not words:
            words = estimate_words(text, len(raw) / SR)
        audio, words = tighten(raw, words)
        write_wav(os.path.join(OUT, f"voice_{i}.wav"), audio)
        metas[i] = {"engine": used, "rate": rate, "text": text, "duration": len(audio) / SR,
                    "raw_duration": len(raw) / SR, "words": words}
    return used, metas


def main():
    os.makedirs(OUT, exist_ok=True)
    rate = int(config.TTS_RATE.rstrip("%"))
    engine = None
    while True:
        engine, metas = synth_all(rate, engine)
        total = sum(m["duration"] + config.SCENE_PAD for m in metas.values())
        print(f"[tts] motor={engine} hız={rate:+d}% toplam={total:.2f}s")
        if not config.FIT_TO_MAX or total <= config.MAX_TOTAL or rate >= config.MAX_RATE:
            break
        rate += 2
    for i, m in metas.items():
        with open(os.path.join(OUT, f"voice_{i}.json"), "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
        print(f"[tts] sahne {i}: {m['duration']:.2f}s — {m['text']}")
    with open(os.path.join(OUT, "engine.json"), "w") as f:
        json.dump({"engine": engine, "rate": rate, "total": total}, f)


if __name__ == "__main__":
    main()
