"""
"500 TL'den GTA 6'ya" — BÖLÜM AYARLARI
=====================================
Yeni bölüm üretmek için SADECE bu dosyayı düzenle, sonra:  python3 build.py

Seslendirme metinleri aşağıdaki değerlerden otomatik üretilir
(sayılar Türkçe yazıya çevrilir), istersen VOICE_OVERRIDES ile elle yazabilirsin.
"""

# --- Telegram / marka ---------------------------------------------------------
BOT_USERNAME = "@goleoaibot"        # Telegram bot kullanıcı adı (ekrandaki @...)
BOT_NAME = "GOLEO BOT"              # Butondaki yazı
BRAND = "GOLEO"                     # En alttaki küçük yazıdaki marka

# --- Bölüm / kasa -------------------------------------------------------------
STEP = 2                            # Kaçıncı adım (2 -> "2. ADIM", seste "ikinci adım")
BANKROLL = 850                      # Bu adımdaki kasa (TL)
PREV_BANKROLL = 500                 # Önceki adımın kasası (sayaç buradan başlar; 1. adımda 0)
START_BANKROLL = 500                # Serinin başlangıç kasası (başlıkta "500 TL → GTA 6")
GOAL_TL = 5000                      # GTA 6 hedef tutarı (ilerleme çubuğu bunun yüzdesi)

# --- Maç ve tercih ------------------------------------------------------------
HOME_TEAM = "Galatasaray"
AWAY_TEAM = "Aston Villa"
PICK = "DEPLASMAN 1.5 ÜST"                  # Ekranda görünen tercih
PICK_SPOKEN = "deplasman bir buçuk üst"     # Seste okunan hâli
ODDS = 1.65

# --- Seslendirme --------------------------------------------------------------
TTS_VOICE = "tr-TR-AhmetNeural"
TTS_RATE = "+6%"         # doğal ton için düşük tutuldu
MAX_PAUSE = 0.30         # cümle arası duraklama üst sınırı (sn) — büyüdükçe daha doğal
SCENE_PAD = 0.4          # sahne süresi = ses süresi + SCENE_PAD
# Toplam süre MAX_TOTAL'ı aşarsa hız %2'lik adımlarla (en fazla MAX_RATE) artırılır.
FIT_TO_MAX = True
MAX_TOTAL = 22.5
MAX_RATE = 10
# Sahne metnini elle yazmak istersen: {1: "...", 3: "..."} gibi doldur.
VOICE_OVERRIDES = {}

# --- Çıktı --------------------------------------------------------------------
OUTPUT_NAME = f"goleo_500tl_gta6_bolum{STEP}"


# ============================================================================
# Aşağısı türetilen değerler — normalde dokunmana gerek yok.
# ============================================================================
from numtr import num_to_words, ordinal_words, decimal_to_words  # noqa: E402

NEW_BANKROLL = round(BANKROLL * ODDS, 2)   # 850 × 1.65 = 1402.50 (kuruş korunur)
NEXT_STEP = STEP + 1


def fmt_tl(x):
    """850 -> '850', 1250 -> '1.250', 1402.5 -> '1.402,50' (Türkçe biçim)."""
    if abs(x - round(x)) < 0.005:
        return f"{int(round(x)):,}".replace(",", ".")
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def money_words(x, dative=False):
    """1402.5 -> 'bin dört yüz iki buçuk lira' (dative=True -> '... liraya')."""
    lira = int(x)
    kurus = int(round((x - lira) * 100))
    L = "liraya" if dative else "lira"
    if kurus == 50:
        return f"{num_to_words(lira)} buçuk {L}"
    if kurus:
        return f"{num_to_words(lira)} lira {num_to_words(kurus)} {'kuruşa' if dative else 'kuruş'}"
    return f"{num_to_words(lira)} {L}"


def fmt_odds(x):
    return f"{x:.2f}"


def voice_texts():
    if STEP == 1:
        t = {
            1: f"{num_to_words(START_BANKROLL).capitalize()} liradan GTA 6'ya! "
               f"{ordinal_words(STEP).capitalize()} adım başlıyor.",
            2: f"Başlangıç kasamız {num_to_words(BANKROLL)} lira.",
        }
    else:
        t = {
            1: f"{'İlk' if STEP == 2 else ordinal_words(STEP - 1).capitalize()} kupon tuttu! "
               f"{num_to_words(START_BANKROLL).capitalize()} liradan GTA 6'ya, "
               f"{ordinal_words(STEP)} adımdayız.",
            2: f"Kasamız şimdi {money_words(BANKROLL)}.",
        }
    t[3] = (f"Bugün {HOME_TEAM}, {AWAY_TEAM} maçı var. Tercihimiz {PICK_SPOKEN}. "
            f"Oran {decimal_to_words(ODDS)}.")
    t[4] = (f"Tutarsa kasamız {money_words(NEW_BANKROLL, dative=True)} çıkıyor, "
            f"{ordinal_words(NEXT_STEP)} adıma geçiyoruz.")
    t[5] = "Ücretsiz tercihlerin hepsi Telegram'da, Goleo Bot'ta. Takipte kal!"
    t.update(VOICE_OVERRIDES)
    return t
