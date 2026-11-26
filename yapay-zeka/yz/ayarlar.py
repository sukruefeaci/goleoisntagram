from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
DURUM = KOK / "durum"            # git'e girer: model, hafıza, rapor
ONBELLEK = KOK / "veri" / "onbellek"  # indirilen ham veri (git'e girmez)

MODEL_DOSYA = DURUM / "model.json"
TAHMIN_DOSYA = DURUM / "tahminler.csv"
ELLE_DOSYA = DURUM / "elle_sonuclar.csv"
RAPOR_DOSYA = DURUM / "RAPOR.md"

# lig kodu: (ad, openfootball dosyası, football-data.co.uk kodu)
LIGLER = {
    "tr": ("Süper Lig", "tr.1", "T1"),
    "en": ("Premier League", "en.1", "E0"),
    "es": ("LaLiga", "es.1", "SP1"),
    "de": ("Bundesliga", "de.1", "D1"),
    "it": ("Serie A", "it.1", "I1"),
    "fr": ("Ligue 1", "fr.1", "F1"),
}

SEZON_SAYISI = 5          # kaç sezon geriye veri çekilsin
EGITIM_GUN = 1100         # modele en fazla kaç günlük geçmiş girsin
TEST_GUN = 365            # öz-değerlendirme (backtest) penceresi
BLOK_GUN = 14             # backtest'te kaç günde bir yeniden eğitilsin
DENEME_SAYISI = 6         # her güncellemede denenecek yeni "mutant" ayar sayısı
FIKSTUR_GUN = 10          # kaç gün sonrasına kadar maç tahmin edilsin

VARSAYILAN = {"xi": 0.0025, "reg": 3.0, "rho": -0.05, "w_elo": 0.2, "K": 25, "T": 1.0}
