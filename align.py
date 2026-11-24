"""Kendi seslendirmeni (ör. ElevenLabs, tek parça) videoya uyarlar.

    python3 align.py ses_dosyasi.mp3      (build.py --voice ses.mp3 bunu otomatik çağırır)

1) Aynı metni edge-tts ile referans olarak üretir (kelime zamanları bilinir).
2) Kayıt ile referansı DTW (log-mel öznitelikleri) ile hizalar.
3) Referanstaki sahne sınırlarını kayda taşır, en yakın sessizliğe oturtur.
4) Kaydı sahnelere böler: build/audio/voice_N.wav + voice_N.json (kelime zamanları).
"""
import json
import os
import sys

import numpy as np

import config
import tts

SR = tts.SR
HOP = 0.02  # 20 ms
OUT = tts.OUT


def logmel(a, n_mels=40):
    n_fft = 1024
    hop = int(SR * HOP)
    win = np.hanning(n_fft)
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(a, (n_fft // 2, n_fft // 2)), n_fft)[::hop]
    spec = np.abs(np.fft.rfft(frames * win, axis=1)) ** 2
    f = np.fft.rfftfreq(n_fft, 1 / SR)
    mel = lambda x: 2595 * np.log10(1 + x / 700)  # noqa: E731
    pts = 700 * (10 ** (np.linspace(mel(80), mel(7600), n_mels + 2) / 2595) - 1)
    fb = np.zeros((n_mels, len(f)))
    for i in range(n_mels):
        l, c, r = pts[i], pts[i + 1], pts[i + 2]
        fb[i] = np.clip(np.minimum((f - l) / (c - l), (r - f) / (r - c)), 0, None)
    m = np.log(spec @ fb.T + 1e-8)
    m -= m.mean(0)
    m /= m.std(0) + 1e-6
    return m


def dtw_path(A, B):
    """A (n×d), B (m×d) -> eşleşme yolu [(i, j)]; kosinüs uzaklığı."""
    An = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
    Bn = B / (np.linalg.norm(B, axis=1, keepdims=True) + 1e-9)
    C = 1 - An @ Bn.T
    n, m = C.shape
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0
    for i in range(1, n + 1):
        Ci = C[i - 1]
        prev = D[i - 1]
        row = D[i]
        diag_up = np.minimum(prev[:-1], prev[1:])  # (i-1, j-1) ve (i-1, j)
        tmp = Ci + diag_up
        # yatay bağımlılık (i, j-1): ardışık tarama
        for j in range(1, m + 1):
            v = tmp[j - 1]
            h = row[j - 1] + Ci[j - 1]
            row[j] = v if v < h else h
    i, j, path = n, m, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        k = np.argmin((D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]))
        if k == 0:
            i, j = i - 1, j - 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    return path[::-1]


def silences(a, thr_db=-38, min_len=0.1):
    hop = int(SR * 0.01)
    n = len(a) // hop
    rms = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1))
    quiet = 20 * np.log10(rms + 1e-9) < thr_db
    out, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * 0.01 >= min_len:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return out


def boundary_flags(text, words):
    """Noktalama işaretinden (. , ! ? :) sonra gelen kelimeler True."""
    toks = text.split()
    flags, ti, prev_punct = [], 0, True
    for w in words:
        key = w["word"].strip(".,!?:;…").lower()
        while ti < len(toks) and toks[ti].strip(".,!?:;…").lower() != key:
            ti += 1
        if ti < len(toks):
            flags.append(prev_punct if ti > 0 else False)
            prev_punct = toks[ti][-1] in ".,!?:;…"
            ti += 1
        else:
            flags.append(False)
    return flags


def snap_to_pauses(words, seg, text):
    """Sahne içindeki duraklamadan sonra gelen cümle/virgül başı kelimeyi duraklamanın
    bitişine oturt (DTW'nin bu noktalardaki ±0.3 sn kaymasını düzeltir)."""
    flags = boundary_flags(text, words)
    cand = [k for k, f in enumerate(flags) if f]
    pauses = [p for p in silences(seg, min_len=0.12) if p[0] > 0.05 and p[1] < len(seg) / SR - 0.05]
    for p0, p1 in pauses:
        if not cand:
            break
        k = min(cand, key=lambda q: abs(words[q]["start"] - p1))
        if abs(words[k]["start"] - p1) > 0.5:
            continue
        words[k]["start"] = round(p1, 3)
        if k > 0:
            words[k - 1]["end"] = round(min(words[k - 1]["end"], p0), 3)
    for k in range(1, len(words)):  # sıralamayı koru
        if words[k]["start"] < words[k - 1]["start"]:
            words[k]["start"] = words[k - 1]["start"]
    return words


def main(path):
    tts.main()  # referans (edge-tts) — kelime zamanları için
    texts = config.voice_texts()
    gap = 0.5
    ref_parts, ref_words, bounds, t = [], [], [], 0.0
    for i in texts:
        a = tts.decode(os.path.join(OUT, f"voice_{i}.wav"))
        meta = json.load(open(os.path.join(OUT, f"voice_{i}.json"), encoding="utf-8"))
        ref_parts += [a, np.zeros(int(gap * SR))]
        ref_words += [{**w, "scene": i, "start": w["start"] + t, "end": w["end"] + t} for w in meta["words"]]
        bounds.append((t, t + len(a) / SR))
        t += len(a) / SR + gap
    ref = np.concatenate(ref_parts)
    rec = tts.decode(path)

    print("[align] DTW hizalama…")
    p = dtw_path(logmel(ref), logmel(rec))
    ri = np.array([a for a, _ in p]) * HOP
    rj = np.array([b for _, b in p]) * HOP

    def to_rec(tr):
        k = np.searchsorted(ri, tr)
        return float(rj[min(k, len(rj) - 1)])

    # sahne sınırları: referanstaki boşluk ortası -> kayıt; en yakın sessizliğe yapıştır
    sil = silences(rec)
    cuts = []
    for k in range(len(bounds) - 1):
        mid = to_rec((bounds[k][1] + bounds[k + 1][0]) / 2)
        best = min(sil, key=lambda s: abs((s[0] + s[1]) / 2 - mid)) if sil else (mid, mid)
        if abs((best[0] + best[1]) / 2 - mid) > 0.6:
            best = (mid, mid)
        cuts.append(best)
        print(f"[align] sahne {k + 1}|{k + 2} sınırı ≈ {mid:.2f}s -> sessizlik {best[0]:.2f}-{best[1]:.2f}s")

    # sahnelere böl
    loud = [s for s in silences(rec, min_len=0.05)]
    starts = [0.0] + [c[1] for c in cuts]
    ends = [c[0] for c in cuts] + [len(rec) / SR]
    # baş/son sessizliği kırp
    first_sound = loud[0][1] if loud and loud[0][0] < 0.02 else 0.0
    starts[0] = max(0.0, first_sound - 0.02)
    if loud and loud[-1][1] >= len(rec) / SR - 0.02:
        ends[-1] = loud[-1][0] + 0.05
    for k, i in enumerate(texts):
        s0, s1 = max(0.0, starts[k] - 0.03), ends[k] + 0.06
        seg = rec[int(s0 * SR): int(s1 * SR)].copy()
        f = int(SR * 0.01)
        seg[:f] *= np.linspace(0, 1, f)
        seg[-f:] *= np.linspace(1, 0, f)
        tts.write_wav(os.path.join(OUT, f"voice_{i}.wav"), seg)
        words = []
        for w in ref_words:
            if w["scene"] != i:
                continue
            ws = min(max(0.0, to_rec(w["start"]) - s0), len(seg) / SR)
            we = min(max(ws, to_rec(w["end"]) - s0), len(seg) / SR)
            words.append({"word": w["word"], "start": round(ws, 3), "end": round(we, 3)})
        words = snap_to_pauses(words, seg, texts[i])
        meta = {"engine": "kullanıcı kaydı", "source": os.path.basename(path), "text": texts[i],
                "duration": len(seg) / SR, "words": words}
        with open(os.path.join(OUT, f"voice_{i}.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)
        print(f"[align] sahne {i}: {s0:.2f}-{s1:.2f}s ({len(seg) / SR:.2f}s) "
              + " ".join(f"{w['word']}@{w['start']:.2f}" for w in words))
    with open(os.path.join(OUT, "engine.json"), "w") as fh:
        json.dump({"engine": f"kullanıcı kaydı ({os.path.basename(path)})", "rate": 0}, fh)


if __name__ == "__main__":
    main(sys.argv[1])
