"""Tek komutla bölüm üretimi:  python3 build.py   (önce config.py'yi düzenle)

1) tts.py      -> her sahnenin sesi ayrı (build/audio/voice_N.wav) + süre/kelime zamanları
2) render.py   -> her sahne ayrı mp4 (build/scenes/sceneN.mp4), paralel
3) ffmpeg      -> sahneleri birleştir
4) audio.py    -> seslendirme + beat + efekt miksi (-14 LUFS)
5) çıktı       -> output/<OUTPUT_NAME>.mp4 ve output/<OUTPUT_NAME>_seslendirme.mp3

  --skip-tts : sesleri yeniden üretmeden (mevcut build/audio ile) render al
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

import audio
import config
import render
import tts


def run(cmd):
    subprocess.run(cmd, check=True)


def main():
    os.makedirs("build/scenes", exist_ok=True)
    os.makedirs("build/mix", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    if "--skip-tts" not in sys.argv:
        tts.main()
    with open("build/audio/engine.json") as f:
        eng = json.load(f)

    scenes = render.build_scenes()
    starts, acc = [], 0
    for s in scenes:
        starts.append(acc / render.FPS)
        acc += s.frames
    total = acc / render.FPS
    print(f"[build] sahne süreleri: {[round(s.frames / render.FPS, 2) for s in scenes]}  toplam={total:.2f}s")

    # 2) sahneleri ayrı ayrı render et
    paths = [f"build/scenes/scene{i + 1}.mp4" for i in range(len(scenes))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        list(ex.map(render.render_scene, range(len(scenes)), starts, paths))

    # 3) birleştir
    with open("build/scenes/list.txt", "w") as f:
        for p in paths:
            f.write(f"file '{os.path.basename(p)}'\n")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "build/scenes/list.txt",
         "-c", "copy", "build/video_silent.mp4"])

    # 4) ses
    voice_clips = [(st + render.VO, f"build/audio/voice_{s.n}.wav") for st, s in zip(starts, scenes)]
    events = sorted((st + t, k) for st, s in zip(starts, scenes) for (t, k) in s.events)
    with open("build/sfx_events.json", "w") as f:
        json.dump(events, f)
    mix_wav, voice_wav = audio.mix(total, voice_clips, events, "build/mix")

    # 5) çıktılar
    out = f"output/{config.OUTPUT_NAME}.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", "build/video_silent.mp4", "-i", mix_wav,
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-ac", "2", "-t", f"{total:.3f}", "-movflags", "+faststart", out])
    mp3 = f"output/{config.OUTPUT_NAME}_seslendirme.mp3"
    run(["ffmpeg", "-y", "-v", "error", "-i", voice_wav, "-c:a", "libmp3lame", "-b:a", "192k", mp3])

    m = audio.measure(out)
    print(f"[build] TTS: {eng['engine']} (hız {eng['rate']:+d}%)")
    print(f"[build] Loudness: {m['input_i']} LUFS, true-peak {m['input_tp']} dBTP")
    print(f"[build] Video: {out}\n[build] Seslendirme: {mp3}")


if __name__ == "__main__":
    main()
