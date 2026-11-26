# GOLEO YZ — kendini geliştiren maç tahmin yapay zekası

API yok, ücretli servis yok. Tamamen ücretsiz veriyle, kendi bilgisayarında ya da
GitHub Actions'ta çalışır ve **her gün kendini yeniden eğitir**.

## Nasıl öğreniyor?

1. **Veri:** football-data.co.uk (sonuçlar + bahis oranları). Ulaşılamazsa openfootball (GitHub).
   Ligler: Süper Lig, Premier League, LaLiga, Bundesliga, Serie A, Ligue 1. Son 5 sezon.
2. **Model:** zaman ağırlıklı Dixon-Coles Poisson (takımların atak ve savunma gücü) ile Elo
   reytinginin karışımı. Sonuçta MS 1/X/2, çifte şans, 1.5/2.5/3.5 alt/üst, KG var/yok ve
   en olası skor olasılıkları çıkar.
3. **Sınav:** Son 1 yılın maçlarını, her 14 günde bir yalnızca o güne kadarki veriyle
   yeniden eğitilerek tahmin eder (geleceği görmeden).
4. **Evrim:** Mevcut "şampiyon" ayarlar ile rastgele mutasyona uğramış yeni ayarlar aynı
   sınava girer. Hatası düşük olan kazanır ve `durum/model.json` dosyasına yazılır.
   Her gün yeni maçlar eklendikçe ve yeni ayarlar denendikçe model iyileşir.
5. **Hafıza:** Maçtan önce yaptığı tahminleri `durum/tahminler.csv` dosyasına kaydeder,
   sonuç gelince puanlar. Gerçek karne `durum/RAPOR.md` dosyasında tutulur.

## Kurulum

```bash
cd yapay-zeka
pip install -r requirements.txt
python ai.py guncelle            # ilk eğitim (~1 dk)
```

## Kullanım

```bash
python ai.py tahmin Galatasaray Fenerbahçe
python ai.py tahmin Arsenal Chelsea --oran 1.90 3.60 4.20   # değerli bahis kontrolü
python ai.py fikstur --lig tr --gun 7                         # yaklaşan maçlar
python ai.py rapor
python ai.py sonuc-ekle tr 2026-11-21 Kocaelispor Fenerbahçe 1 2   # eksik maçı elle ekle
```

## Otomatik günlük öğrenme

`.github/workflows/yapay-zeka.yml` her gün 08:17'de (TSİ) `guncelle` komutunu çalıştırır ve
öğrendiklerini repoya commit'ler. GitHub Actions bu kullanım için ücretsizdir. Hemen
çalıştırmak için: GitHub → Actions → "GOLEO YZ - günlük öğrenme" → Run workflow.

## Dürüst not

Futbolda hiçbir model sonucu garanti etmez. Bu YZ olasılık üretir. Gerçek başarının
ölçüsü, raporda bahisçi oranlarıyla kıyaslanan hata değeri ve değer bahsi ROI'sidir.
