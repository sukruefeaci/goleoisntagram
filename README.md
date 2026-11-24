# GOLEO — "500 TL'den GTA 6'ya" Reels üretici

Python + Pillow + ffmpeg ile 1080×1920, 30 fps, H.264 dikey video; edge-tts seslendirme.

## Yeni bölüm

1. `config.py` dosyasının üst kısmını düzenle:

| Değişken | Ne işe yarar |
|---|---|
| `BOT_USERNAME` | CTA'daki `@KULLANICI_ADI` |
| `BOT_NAME`, `BRAND` | Buton yazısı (`GOLEO BOT`) ve alttaki marka |
| `STEP` | Adım numarası (`1. ADIM`, seste "Birinci adım", sonraki adım otomatik) |
| `BANKROLL` | Bu adımın kasası (sahne 2 sayacı, sahne 4 hesabı) |
| `PREV_BANKROLL` | Önceki adımın kasası; sahne 2 sayacı buradan başlar, 2. adımdan itibaren "N. KUPON TUTTU ✅" rozeti çıkar |
| `START_BANKROLL` | Serinin başlangıcı (başlıktaki `500 TL → GTA 6`) |
| `GOAL_TL` | GTA 6 hedefi; ilerleme çubuğu `kasa / GOAL_TL` |
| `HOME_TEAM`, `AWAY_TEAM` | Maç kartı + seslendirme |
| `PICK` / `PICK_SPOKEN` | Ekrandaki tercih / seste okunan hâli |
| `ODDS` | Oran (yeni kasa = `BANKROLL × ODDS`, otomatik) |
| `TTS_RATE`, `MAX_PAUSE` | Konuşma hızı ve cümle arası duraklama (düşük hız + uzun duraklama = daha doğal) |
| `MAX_TOTAL`, `MAX_RATE`, `FIT_TO_MAX` | Süre sınırı; aşılırsa hız en fazla `MAX_RATE`'e kadar artırılır |
| `VOICE_OVERRIDES` | Bir sahnenin seslendirme metnini elle yazmak için |

Sayılar seslendirme için otomatik Türkçe yazıya çevrilir (`numtr.py`): 850 → "sekiz yüz elli", 1.70 → "bir virgül yetmiş", 1.402,50 → "bin dört yüz iki buçuk lira". Yeni kasa kuruşuyla birlikte tutulur.

2. Çalıştır:

```bash
pip install edge-tts      # bir kez
python3 build.py          # -> output/<OUTPUT_NAME>.mp4 ve _seslendirme.mp3
python3 build.py --skip-tts   # sadece görsel değiştiyse, sesi yeniden üretmez
python3 render.py 3           # tek sahne önizleme -> build/preview/scene3.png
python3 build.py --voice voice/kayit.mp3   # kendi tek parça kaydınla (ElevenLabs vb.)
```

## Dosyalar

- `tts.py`: her sahnenin sesi ayrı; edge-tts → gTTS → Piper sırasıyla dener; kelime zamanlarını kaydeder, uzun duraksamaları kısaltır
- `align.py`: kendi kaydını aynı metnin edge-tts sürümüyle DTW ile hizalar, sahnelere böler ve kelime zamanlarını çıkarır (metin `config.py`'deki ile aynı kelimeleri içermeli)
- `render.py`: sahneler (animasyonlar kelime zamanlarına bağlı), güvenli alan: üst/alt 250 px
- `audio.py`: kodla üretilen beat / whoosh / tık / ding; seslendirme -14 LUFS, beat ~20 dB altında, final -14 LUFS
- `build.py`: hepsini sırayla çalıştırır, sahneleri ayrı render edip ffmpeg ile birleştirir
