"""Ses miksi: seslendirme (-14 LUFS) + kodla üretilmiş beat (~20 dB altında) + whoosh/tık efektleri.

Hepsi numpy ile sentezlenir (telifsiz). Loudness ölçümü/normalizasyon ffmpeg loudnorm ile.
"""
import json
import re
import subprocess

import numpy as np

SR = 48000
rng = np.random.default_rng(7)


# ----------------------------------------------------------------------------- dsp yardımcıları
def env_exp(n, decay):
    return np.exp(-np.arange(n) / (SR * decay))


def onepole_lp(x, cutoff):
    """cutoff skaler ya da örnek başına dizi (Hz)."""
    cutoff = np.broadcast_to(np.asarray(cutoff, float), x.shape)
    a = 1 - np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):  # kısa sesler için yeterince hızlı
        s += a[i] * (x[i] - s)
        y[i] = s
    return y


def lp_fast(x, cutoff):
    """Sabit kesimli tek kutuplu alçak geçiren (scipy'siz, vektörel)."""
    from numpy.fft import irfft, rfft, rfftfreq
    X = rfft(x)
    f = rfftfreq(len(x), 1 / SR)
    return irfft(X / (1 + 1j * f / cutoff), len(x))


def hp_fast(x, cutoff):
    return x - lp_fast(x, cutoff)


# ----------------------------------------------------------------------------- efektler
def whoosh(dur=0.42):
    n = int(SR * dur)
    t = np.linspace(0, 1, n)
    noise = rng.standard_normal(n)
    sweep = 400 + 5200 * np.sin(np.pi * t) ** 2          # filtre yukarı-aşağı süpürür
    y = onepole_lp(noise, sweep) - onepole_lp(noise, sweep * 0.25)
    amp = np.sin(np.pi * t) ** 1.6
    y = y * amp
    return 0.9 * y / (np.abs(y).max() + 1e-9)


def tick():
    n = int(SR * 0.03)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * 2600 * t) * env_exp(n, 0.006)
    y += 0.4 * rng.standard_normal(n) * env_exp(n, 0.002)
    return 0.55 * y / np.abs(y).max()


def ding():
    n = int(SR * 0.45)
    t = np.arange(n) / SR
    y = (np.sin(2 * np.pi * 1318.5 * t) + 0.6 * np.sin(2 * np.pi * 1975.5 * t)
         + 0.25 * np.sin(2 * np.pi * 2637 * t)) * env_exp(n, 0.12)
    return 0.8 * y / np.abs(y).max()


def pop():
    n = int(SR * 0.12)
    t = np.arange(n) / SR
    f = 900 * np.exp(-t * 25) + 250
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_exp(n, 0.04)
    return 0.8 * y / np.abs(y).max()


SFX = {"whoosh": (whoosh, 1.0), "tick": (tick, 0.55), "ding": (ding, 0.75), "pop": (pop, 0.7)}


# ----------------------------------------------------------------------------- beat
def beat(total, bpm=124):
    n = int(SR * total)
    out = np.zeros(n)
    spb = 60 / bpm
    # kick
    kn = int(SR * 0.32)
    kt = np.arange(kn) / SR
    kf = 45 + 110 * np.exp(-kt * 30)
    kick = np.sin(2 * np.pi * np.cumsum(kf) / SR) * env_exp(kn, 0.11)
    # hi-hat
    hn = int(SR * 0.05)
    hat = hp_fast(rng.standard_normal(hn), 7000) * env_exp(hn, 0.012)
    hat /= np.abs(hat).max()
    # clap/snare
    sn = int(SR * 0.18)
    snare = hp_fast(rng.standard_normal(sn), 1500) * env_exp(sn, 0.05)
    snare /= np.abs(snare).max()

    def add(sig, t0, g):
        i = int(t0 * SR)
        if i >= n:
            return
        j = min(n, i + len(sig))
        out[i:j] += g * sig[: j - i]

    b = 0
    while b * spb < total:
        t0 = b * spb
        add(kick, t0, 1.0)
        if b % 2 == 1:
            add(snare, t0, 0.35)
        add(hat, t0 + spb / 2, 0.22)
        add(hat, t0, 0.12)
        b += 1
    # pad: Am - F - C - G akorları, yumuşak testere + alçak geçiren
    chords = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (130.81, 196.0, 261.63 * 1.0),
              (196.0, 246.94, 293.66)]
    bar = spb * 4
    t = np.arange(n) / SR
    pad = np.zeros(n)
    for k in range(int(np.ceil(total / bar))):
        i0, i1 = int(k * bar * SR), min(n, int((k + 1) * bar * SR))
        tt = t[i0:i1]
        seg = np.zeros(i1 - i0)
        for f in chords[k % 4]:
            for det in (-0.4, 0.4):
                ph = (tt * (f + det)) % 1.0
                seg += 2 * ph - 1
        fade = np.minimum(1, np.minimum((tt - tt[0]) / 0.05, (tt[-1] - tt + 1e-3) / 0.05))
        pad[i0:i1] = seg * fade
    pad = lp_fast(pad, 900)
    pad = pad / (np.abs(pad).max() + 1e-9) * (0.5 + 0.1 * np.sin(2 * np.pi * 0.25 * t))
    # sidechain hissi: kick'te pad'i kıs
    duck = 1 - 0.5 * np.exp(-((t % spb) / 0.09))
    out += 0.45 * pad * duck
    # baş/son fade
    f_in, f_out = int(SR * 0.05), int(SR * 0.6)
    out[:f_in] *= np.linspace(0, 1, f_in)
    out[-f_out:] *= np.linspace(1, 0, f_out)
    return out / (np.abs(out).max() + 1e-9) * 0.8


# ----------------------------------------------------------------------------- loudness
def write_wav(path, a):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f64le", "-ar", str(SR), "-ac", "1",
                    "-i", "-", "-c:a", "pcm_s24le", path], input=a.astype(np.float64).tobytes(),
                   check=True)


def read_wav(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f64le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float64).copy()


def measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af",
                        "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    js = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S).group(0)
    return json.loads(js)


def loudnorm(src, dst, target, tp=-1.0):
    """İki geçişli EBU R128 normalizasyonu (lineer)."""
    m = measure(src)
    af = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:"
          f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-af", af, "-ar", str(SR),
                    "-c:a", "pcm_s24le", dst], check=True)


def gain_to_lufs(src, dst, target):
    """Sabit kazançla hedef LUFS'a getir (beat gibi dinamik olmayan stemler için)."""
    m = measure(src)
    g = 10 ** ((target - float(m["input_i"])) / 20)
    write_wav(dst, read_wav(src) * g)


# ----------------------------------------------------------------------------- miks
def mix(total, voice_clips, sfx_events, out_dir, voice_lufs=-14.0, bed_db=-20.0):
    """voice_clips: [(başlangıç_sn, wav_yolu)], sfx_events: [(zaman_sn, tür)]"""
    n = int(round(total * SR))
    voice = np.zeros(n)
    for t0, path in voice_clips:
        a = read_wav(path)
        i = int(round(t0 * SR))
        j = min(n, i + len(a))
        voice[i:j] += a[: j - i]
    write_wav(f"{out_dir}/voice_raw.wav", voice)
    loudnorm(f"{out_dir}/voice_raw.wav", f"{out_dir}/voice.wav", voice_lufs, tp=-1.5)

    write_wav(f"{out_dir}/beat_raw.wav", beat(total))
    gain_to_lufs(f"{out_dir}/beat_raw.wav", f"{out_dir}/beat.wav", voice_lufs + bed_db)

    sfx = np.zeros(n)
    cache = {}
    for t0, kind in sfx_events:
        if kind not in cache:
            fn, g = SFX[kind]
            cache[kind] = fn() * g
        s = cache[kind]
        i = int(round(t0 * SR))
        if i >= n:
            continue
        j = min(n, i + len(s))
        sfx[i:j] += s[: j - i]
    write_wav(f"{out_dir}/sfx_raw.wav", sfx)
    # efektler sesin ~10 dB altında
    gain_to_lufs(f"{out_dir}/sfx_raw.wav", f"{out_dir}/sfx.wav", voice_lufs - 10)

    v, b, s = (read_wav(f"{out_dir}/{x}.wav") for x in ("voice", "beat", "sfx"))
    m = np.zeros(n)
    for x in (v, b, s):
        m[: len(x[:n])] += x[:n]
    write_wav(f"{out_dir}/mix_raw.wav", m)
    # son geçiş: toplam -14 LUFS, true-peak -1 dBTP
    loudnorm(f"{out_dir}/mix_raw.wav", f"{out_dir}/mix.wav", voice_lufs, tp=-1.0)
    return f"{out_dir}/mix.wav", f"{out_dir}/voice.wav"
