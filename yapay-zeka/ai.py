#!/usr/bin/env python3
"""GOLEO YZ — kendini geliştiren futbol tahmin yapay zekası.

Kullanım:
  python ai.py guncelle                    # veri çek, karne çıkar, kendini eğit, yeni maçları tahmin et
  python ai.py tahmin Galatasaray Fenerbahçe [--lig tr] [--oran 2.10 3.40 3.20]
  python ai.py fikstur [--lig tr] [--gun 7]
  python ai.py rapor
  python ai.py sonuc-ekle tr 2026-11-21 Kocaelispor Fenerbahçe 1 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import sys
import unicodedata

import numpy as np
import pandas as pd

from yz import ayarlar as A
from yz import hafiza as H
from yz import model as M
from yz import ogrenme as O
from yz import veri as V

TR = str.maketrans("çğıöşüÇĞİÖŞÜâ", "cgiosuCGIOSUa")
EKLER = {"fk", "sk", "as", "jk", "fc", "cf", "afc", "ac", "a.s.", "kulubu", "spor kulubu", "bk", "ssc", "1."}


def sade(ad: str) -> str:
    s = unicodedata.normalize("NFKD", ad.translate(TR).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(p for p in s.replace("-", " ").split() if p not in EKLER)


def takim_bul(ad: str, takimlar) -> str | None:
    harita = {sade(t): t for t in takimlar}
    s = sade(ad)
    if s in harita:
        return harita[s]
    icinde = [t for k, t in harita.items() if s and (s in k or k in s)]
    if len(icinde) == 1:
        return icinde[0]
    yakin = difflib.get_close_matches(s, list(harita), n=1, cutoff=0.6)
    return harita[yakin[0]] if yakin else None


def yuzde(x):
    return f"%{100 * x:.0f}"


def adil(x):
    return f"{1 / x:.2f}" if x > 0 else "-"


def ligleri_sec(lig):
    return [lig] if lig else list(A.LIGLER)


def veri_hepsi(ligler):
    out = {}
    for l in ligler:
        df, kaynak = V.lig_verisi(l)
        out[l] = (df, kaynak)
    return out


def yaklasan(df, gun):
    bugun = pd.Timestamp.now().normalize()
    f = df[df["eg"].isna() & (df["tarih"] >= bugun) & (df["tarih"] <= bugun + pd.Timedelta(days=gun))]
    return f[["tarih", "ev", "dep", "o1", "ox", "o2"]].reset_index(drop=True)


# ---------------------------------------------------------------- komutlar
def guncelle(args):
    durum = O.model_yukle()
    hafiza = H.yukle()
    rng = np.random.default_rng()
    ozet = []
    for lig, (df, kaynak) in veri_hepsi(ligleri_sec(args.lig)).items():
        ad = A.LIGLER[lig][0]
        oynanan = int(df["eg"].notna().sum())
        print(f"\n▶ {ad}: {oynanan} maç ({kaynak})", flush=True)
        islenen = H.sonuclari_isle(hafiza, lig, df)
        if islenen:
            print(f"  hafıza: {islenen} tahminin sonucu geldi, karneye işlendi")
        kayit = O.ogren(lig, df, durum, rng)
        kayit["kaynak"], kayit["son_mac"] = kaynak, str(df.loc[df["eg"].notna(), "tarih"].max())[:10]
        durum[lig] = kayit
        if "sinav" in kayit:
            g = kayit["gecmis"][-1]
            print(f"  nesil {kayit['nesil']}: hata {g['eski_skor']:.4f} → {g['skor']:.4f} "
                  f"{'✅ GELİŞTİ' if g['gelisti'] else '(şampiyon korundu)'}  ayar={kayit['ayar']}")
            fx = yaklasan(df, A.FIKSTUR_GUN)
            if len(fx):
                t = M.tahmin_et(df, fx, kayit["ayar"])
                hafiza = H.tahmin_ekle(hafiza, lig, t, kayit["nesil"])
                print(f"  {len(fx)} yaklaşan maç tahmin edildi")
        else:
            print(f"  atlandı: {kayit.get('not')}")
        ozet.append(lig)
    O.model_kaydet(durum)
    H.kaydet(hafiza)
    rapor_yaz(durum, hafiza)
    print(f"\nKaydedildi → {A.RAPOR_DOSYA}")


def tahmin(args):
    durum = O.model_yukle()
    ligler = ligleri_sec(args.lig)
    veriler = veri_hepsi(ligler)
    for lig, (df, _) in veriler.items():
        takimlar = pd.unique(pd.concat([df["ev"], df["dep"]]))
        e, d = takim_bul(args.ev, takimlar), takim_bul(args.dep, takimlar)
        if e and d:
            break
    else:
        print("Takım(lar) bulunamadı. Lig belirtmeyi deneyin: --lig tr|en|es|de|it|fr")
        return 1
    ayar = durum.get(lig, {}).get("ayar", A.VARSAYILAN)
    r = M.tahmin_et(df, pd.DataFrame({"ev": [e], "dep": [d]}), ayar).iloc[0]
    print(f"\n⚽ {e} - {d}   ({A.LIGLER[lig][0]}, model nesli {durum.get(lig, {}).get('nesil', 0)})")
    print(f"Beklenen gol: {r['xg_ev']:.2f} - {r['xg_dep']:.2f}   En olası skor: {r['skor']}\n")
    s = M.secenekler(r)
    oranlar = dict(zip(["1", "X", "2"], args.oran)) if args.oran else {}
    print(f"{'Seçenek':<10}{'Olasılık':>9}{'Adil oran':>11}" + (f"{'Oran':>8}{'Değer':>8}" if oranlar else ""))
    for k, v in sorted(s.items(), key=lambda x: -x[1]):
        satir = f"{M.ETIKET[k]:<10}{yuzde(v):>9}{adil(v):>11}"
        if k in oranlar:
            deger = v * oranlar[k] - 1
            satir += f"{oranlar[k]:>8.2f}{deger:>+8.0%}" + ("  ← DEĞERLİ" if deger > 0.05 else "")
        print(satir)
    k, kp = M.en_iyi_secim(r)
    print(f"\n🤖 YZ seçimi: {M.ETIKET[k]} ({yuzde(kp)}, adil oran {adil(kp)})")
    print("Not: Olasılıktır, garanti değildir.")


def fikstur(args):
    durum = O.model_yukle()
    for lig, (df, _) in veri_hepsi(ligleri_sec(args.lig)).items():
        fx = yaklasan(df, args.gun)
        if not len(fx):
            continue
        t = M.tahmin_et(df, fx, durum.get(lig, {}).get("ayar", A.VARSAYILAN))
        print(f"\n== {A.LIGLER[lig][0]} ==")
        for _, r in t.iterrows():
            k, kp = M.en_iyi_secim(r)
            print(f"{str(r['tarih'])[:10]}  {r['ev']:>24} - {r['dep']:<24} 1:{yuzde(r['p1']):>4} X:{yuzde(r['px']):>4}"
                  f" 2:{yuzde(r['p2']):>4}  Ü2.5:{yuzde(r['pU2.5']):>4}  → {M.ETIKET[k]} ({yuzde(kp)})")


def sonuc_ekle(args):
    df, _ = V.lig_verisi(args.lig)
    takimlar = pd.unique(pd.concat([df["ev"], df["dep"]]))
    e = takim_bul(args.ev, takimlar) or args.ev
    d = takim_bul(args.dep, takimlar) or args.dep
    V.elle_ekle(args.lig, args.tarih, e, d, args.eg, args.dg)
    print(f"Eklendi: {args.tarih} {e} {args.eg}-{args.dg} {d}  (bir sonraki 'guncelle'de öğrenilecek)")


def rapor(args):
    print(rapor_yaz(O.model_yukle(), H.yukle()))


def rapor_yaz(durum, hafiza) -> str:
    s = [f"# GOLEO YZ Raporu\n\n_Güncelleme: {dt.datetime.now():%Y-%m-%d %H:%M}_\n",
         "Olasılıklar tahmindir, garanti değildir.\n",
         "## Sınav sonuçları (son 1 yıl, geleceği görmeden)\n",
         "| Lig | Nesil | Maç | MS isabet | 2.5 isabet | Hata (YZ) | Hata (ortalama) | Hata (bahisçi) | Değer bahsi ROI | Kaynak |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for lig, k in durum.items():
        sn = k.get("sinav")
        if not sn:
            continue
        roi = sn.get("roi")
        s.append(f"| {A.LIGLER[lig][0]} | {k['nesil']} | {sn['mac']} | {yuzde(sn['isabet_1x2'])} | "
                 f"{yuzde(sn['isabet_ust'])} | {sn['ll_1x2']:.4f} | {sn['ll_1x2_ortalama']:.4f} | "
                 f"{(f'{sn['ll_1x2_bahisci']:.4f}' if 'll_1x2_bahisci' in sn else '-')} | "
                 f"{(f'{roi['roi']:+.1%} ({roi['bahis']})' if roi else '-')} | {k.get('kaynak', '')} |")
    s.append("\nHata = MS log-loss (düşük daha iyi). 'Bahisçi' sütunu YZ'nin piyasaya ne kadar yaklaştığını gösterir.\n")

    s.append("## Gelişim geçmişi\n")
    for lig, k in durum.items():
        g = k.get("gecmis", [])
        if g:
            gel = sum(x["gelisti"] for x in g)
            s.append(f"- **{A.LIGLER[lig][0]}**: {len(g)} eğitim, {gel} kez gelişti; "
                     f"ilk hata {g[0]['eski_skor']:.4f} → son {g[-1]['skor']:.4f}")

    s.append("\n## Gerçek karne (maçtan önce yapılan tahminler)\n")
    kt = H.karne(hafiza)
    if kt["mac"]:
        s.append(f"Toplam {kt['mac']} maç — MS isabet {yuzde(kt['isabet_1x2'])}, 2.5 isabet {yuzde(kt['isabet_ust'])}, "
                 f"YZ seçimi isabet {yuzde(kt['isabet_secim'])} (beklenen {yuzde(kt['beklenen_secim'])})\n")
        for lig in durum:
            kl = H.karne(hafiza, lig)
            if kl["mac"]:
                s.append(f"- {A.LIGLER[lig][0]}: {kl['mac']} maç, seçim isabeti {yuzde(kl['isabet_secim'])}")
    else:
        s.append("Henüz sonucu gelen tahmin yok.")

    s.append("\n## Yaklaşan maçlar\n")
    bek = hafiza[hafiza["eg"].isna()].sort_values(["tarih", "lig"])
    if len(bek):
        s.append("| Tarih | Lig | Maç | 1 | X | 2 | 2.5 Üst | KG | Skor | YZ seçimi |")
        s.append("|---|---|---|---|---|---|---|---|---|---|")
        for _, r in bek.iterrows():
            s.append(f"| {r['tarih']} | {r['lig']} | {r['ev']} - {r['dep']} | {yuzde(r['p1'])} | {yuzde(r['px'])} | "
                     f"{yuzde(r['p2'])} | {yuzde(r['pU2.5'])} | {yuzde(r['pKG'])} | {r['skor']} | "
                     f"{M.ETIKET[r['secim']]} ({yuzde(r['secim_p'])}, adil {adil(r['secim_p'])}) |")
    else:
        s.append("Veride yaklaşan maç yok.")
    metin = "\n".join(s) + "\n"
    A.DURUM.mkdir(parents=True, exist_ok=True)
    A.RAPOR_DOSYA.write_text(metin, encoding="utf-8")
    return metin


def main():
    ap = argparse.ArgumentParser(description="GOLEO YZ — kendini geliştiren maç tahmin yapay zekası")
    alt = ap.add_subparsers(dest="komut", required=True)
    p = alt.add_parser("guncelle"); p.add_argument("--lig", choices=A.LIGLER); p.set_defaults(f=guncelle)
    p = alt.add_parser("tahmin"); p.add_argument("ev"); p.add_argument("dep")
    p.add_argument("--lig", choices=A.LIGLER); p.add_argument("--oran", type=float, nargs=3, metavar=("1", "X", "2"))
    p.set_defaults(f=tahmin)
    p = alt.add_parser("fikstur"); p.add_argument("--lig", choices=A.LIGLER)
    p.add_argument("--gun", type=int, default=A.FIKSTUR_GUN); p.set_defaults(f=fikstur)
    p = alt.add_parser("rapor"); p.set_defaults(f=rapor)
    p = alt.add_parser("sonuc-ekle"); p.add_argument("lig", choices=A.LIGLER); p.add_argument("tarih")
    p.add_argument("ev"); p.add_argument("dep"); p.add_argument("eg", type=int); p.add_argument("dg", type=int)
    p.set_defaults(f=sonuc_ekle)
    args = ap.parse_args()
    return args.f(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
