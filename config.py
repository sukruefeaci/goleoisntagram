"""
"500 TL'den GTA 6'ya" — BÖLÜM AYARLARI
=====================================
Yeni bölüm üretmek için SADECE bu dosyayı düzenle, sonra:  python3 build.py

Seslendirme metinleri aşağıdaki değerlerden otomatik üretilir
(sayılar Türkçe yazıya çevrilir), istersen VOICE_OVERRIDES ile elle yazabilirsin.
"""

# --- Telegram / marka ---------------------------------------------------------
BOT_USERNAME = "@KULLANICI_ADI"     # Telegram bot kullanıcı adı (ekrandaki @...)
BOT_NAME = "GOLEO BOT"              # Butondaki yazı
BRAND = "GOLEO"                     # En alttaki küçük yazıdaki marka

# --- Bölüm / kasa -------------------------------------------------------------
STEP = 1                            # Kaçıncı adım (1 -> "1. ADIM", seste "Birinci adım")
BANKROLL = 500                      # Bu adımdaki kasa (TL)
START_BANKROLL = 500                # Serinin başlangıç kasası (başlıkta "500 TL → GTA 6")
GOAL_TL = 3500                      # GTA 6 hedef tutarı (ilerleme çubuğu bunun yüzdesi)

# --- Maç ve tercih ------------------------------------------------------------
HOME_TEAM = "Başakşehir"
AWAY_TEAM = "Çorumspor"
PICK = "2.5 ÜST & KG VAR"                         # Ekranda görünen tercih
PICK_SPOKEN = "iki buçuk üst ve karşılıklı gol var"  # Seste okunan hâli
ODDS = 1.70

# --- Seslendirme --------------------------------------------------------------
TTS_VOICE = "tr-TR-AhmetNeural"
TTS_RATE = "+10%"
SCENE_PAD = 0.4          # sahne süresi = ses süresi + SCENE_PAD
# Toplam süre MAX_TOTAL'ı aşarsa hız %2'lik adımlarla (en fazla MAX_RATE) artırılır.
FIT_TO_MAX = True
MAX_TOTAL = 20.0
MAX_RATE = 24
# Sahne metnini elle yazmak istersen: {1: "...", 3: "..."} gibi doldur.
VOICE_OVERRIDES = {}

# --- Çıktı --------------------------------------------------------------------
OUTPUT_NAME = f"goleo_500tl_gta6_bolum{STEP}"


# ============================================================================
# Aşağısı türetilen değerler — normalde dokunmana gerek yok.
# ============================================================================
from numtr import num_to_words, ordinal_words, decimal_to_words  # noqa: E402

NEW_BANKROLL = round(BANKROLL * ODDS)
NEXT_STEP = STEP + 1


def fmt_tl(x):
    """850 -> '850', 1250 -> '1.250' (Türkçe binlik ayırıcı)."""
    return f"{int(round(x)):,}".replace(",", ".")


def fmt_odds(x):
    return f"{x:.2f}"


def voice_texts():
    t = {
        1: f"{num_to_words(START_BANKROLL).capitalize()} liradan GTA 6'ya! "
           f"{ordinal_words(STEP).capitalize()} adım başlıyor.",
        2: (f"Başlangıç kasamız {num_to_words(BANKROLL)} lira." if STEP == 1
            else f"Kasamız şu an {num_to_words(BANKROLL)} lira."),
        3: f"Bugünkü tercih: {HOME_TEAM}, {AWAY_TEAM} maçında {PICK_SPOKEN}. "
           f"Oran {decimal_to_words(ODDS)}.",
        4: f"Tutarsa kasamız {num_to_words(NEW_BANKROLL)} liraya çıkıyor ve "
           f"{ordinal_words(NEXT_STEP)} adıma geçiyoruz.",
        5: "Daha fazla ücretsiz tercih için Telegram'da Goleo Bot'a gel. Takipte kal!",
    }
    t.update(VOICE_OVERRIDES)
    return t
