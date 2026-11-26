"""Kendini geliştirme döngüsü.

Her güncellemede, her lig için:
1. Son TEST_GUN günü "sınav" olarak ayırır. Modeli her BLOK_GUN'de bir yalnızca o
   tarihten önceki maçlarla yeniden eğitip sonraki maçları tahmin ettirir
   (geleceği görmeden, gerçek hayattaki gibi).
2. Mevcut şampiyon ayarlarla birlikte rastgele mutasyona uğramış yeni ayarları
   (xi, reg) ve kalibrasyon ayarlarını (rho, w_elo, K, T) aynı sınava sokar.
3. Daha düşük hata (log-loss) veren ayar şampiyon olur; geçmiş kayıt altına alınır.
Veri arttıkça ve yeni denemeler yapıldıkça model sürekli kendini iyileştirir.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json

import numpy as np
import pandas as pd

from . import ayarlar as A
from . import model as M

RHO = np.round(np.linspace(-0.30, 0.05, 15), 3)
W_ELO = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
KLER = [15, 25, 35]
TLER = np.round(np.linspace(0.70, 1.20, 11), 3)


def _ll(p, y):
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))))


def sinav_seti(df: pd.DataFrame):
    oyn = df[df["eg"].notna()].reset_index(drop=True)
    if len(oyn) < 300:
        return oyn, None
    son = oyn["tarih"].max()
    test = oyn[oyn["tarih"] > son - pd.Timedelta(days=A.TEST_GUN)].copy()
    bas = test["tarih"].min()
    test["blok"] = ((test["tarih"] - bas).dt.days // A.BLOK_GUN).astype(int)
    return oyn, test


def _test_lambda(oyn, test, xi, reg):
    lh = np.empty(len(test)); la = np.empty(len(test))
    for _, idx in test.groupby("blok").indices.items():
        parca = test.iloc[idx]
        lh[idx], la[idx] = M.lambdalar(oyn, parca, parca["tarih"].min().normalize(), xi, reg)
    return lh, la


def degerlendir(oyn, test, adaylar, eloler, beraberlik, sabit=None):
    """Her (xi, reg) adayı için en iyi kalibrasyonu bulur. En iyi sonucu döndürür.
    `sabit` verilirse yalnızca o tam ayar seti puanlanır (şampiyonun bugünkü puanı)."""
    y = np.where(test["eg"] > test["dg"], 0, np.where(test["eg"] == test["dg"], 1, 2))
    y_ust = (test["eg"] + test["dg"] > 2).to_numpy().astype(int)
    en_iyi = None
    for xi, reg in adaylar:
        lh, la = _test_lambda(oyn, test, xi, reg)
        rholar = [sabit["rho"]] if sabit else RHO
        for rho in rholar:
            m = M.pazarlar(M.skor_matrisi(lh, la, rho))
            p_ust = np.stack([1 - m["U2.5"], m["U2.5"]], 1)
            ll_ust = _ll(p_ust, y_ust)
            for K in ([sabit["K"]] if sabit else KLER):
                fark = eloler[K]
                for w, T in itertools.product([sabit["w_elo"]] if sabit else W_ELO,
                                              [sabit["T"]] if sabit else TLER):
                    p3 = M.karistir(m, fark, beraberlik, w, T)
                    ll = _ll(p3, y)
                    skor = ll + ll_ust
                    if en_iyi is None or skor < en_iyi["skor"]:
                        en_iyi = {"skor": skor, "ll_1x2": ll, "ll_ust": ll_ust,
                                  "isabet_1x2": float((p3.argmax(1) == y).mean()),
                                  "isabet_ust": float(((m["U2.5"] > 0.5).astype(int) == y_ust).mean()),
                                  "ayar": {"xi": float(xi), "reg": float(reg), "rho": float(rho),
                                           "w_elo": float(w), "K": int(K), "T": float(T)}}
    return en_iyi


def referanslar(test):
    """Kıyas: (a) lig ortalaması ile tahmin, (b) bahis şirketi oranları (varsa)."""
    y = np.where(test["eg"] > test["dg"], 0, np.where(test["eg"] == test["dg"], 1, 2))
    frek = np.bincount(y, minlength=3) / len(y)
    sonuc = {"ll_1x2_ortalama": _ll(np.tile(frek, (len(y), 1)), y)}
    o = test[["o1", "ox", "o2"]].to_numpy(float)
    ok = np.isfinite(o).all(1) & (o > 1).all(1)
    if ok.sum() > 50:
        ters = 1 / o[ok]
        sonuc["ll_1x2_bahisci"] = _ll(ters / ters.sum(1, keepdims=True), y[ok])
        sonuc["bahisci_mac"] = int(ok.sum())
    return sonuc


def roi(df, test, ayar, beraberlik, esik=0.05):
    """Modelin 'değerli' bulduğu MS bahislerini oranlarla oynasaydık kâr/zarar."""
    o = test[["o1", "ox", "o2"]].to_numpy(float)
    ok = np.isfinite(o).all(1) & (o > 1).all(1)
    if ok.sum() < 50:
        return None
    oyn, _ = sinav_seti(df)
    lh, la = _test_lambda(oyn, test, ayar["xi"], ayar["reg"])
    m = M.pazarlar(M.skor_matrisi(lh, la, ayar["rho"]))
    fark, _ = M.elo_gecir(oyn, ayar["K"])
    p3 = M.karistir(m, fark[test.index.to_numpy()], beraberlik, ayar["w_elo"], ayar["T"])
    y = np.where(test["eg"] > test["dg"], 0, np.where(test["eg"] == test["dg"], 1, 2))
    deger = p3 * o - 1
    bahis = kazanc = 0.0
    for n in np.where(ok)[0]:
        k = int(np.argmax(deger[n]))
        if deger[n, k] > esik:
            bahis += 1
            kazanc += (o[n, k] - 1) if y[n] == k else -1
    return {"bahis": int(bahis), "roi": (kazanc / bahis) if bahis else 0.0}


def model_yukle() -> dict:
    if A.MODEL_DOSYA.exists():
        return json.loads(A.MODEL_DOSYA.read_text(encoding="utf-8"))
    return {}


def model_kaydet(d: dict):
    A.DURUM.mkdir(parents=True, exist_ok=True)
    A.MODEL_DOSYA.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def ogren(lig: str, df: pd.DataFrame, durum: dict, rng: np.random.Generator) -> dict:
    kayit = durum.get(lig, {"ayar": dict(A.VARSAYILAN), "gecmis": [], "nesil": 0})
    oyn, test = sinav_seti(df)
    if test is None:
        kayit["not"] = f"yetersiz veri ({len(oyn)} maç)"
        return kayit
    eloler = {K: M.elo_gecir(oyn, K)[0][test.index.to_numpy()] for K in KLER}
    eloler.update({kayit["ayar"]["K"]: M.elo_gecir(oyn, kayit["ayar"]["K"])[0][test.index.to_numpy()]})
    ber = M.beraberlik_orani(oyn[oyn["tarih"] < test["tarih"].min()])

    s = kayit["ayar"]
    sampiyon = degerlendir(oyn, test, [(s["xi"], s["reg"])], eloler, ber, sabit=s)

    # aday üretimi: ilk seferde geniş ızgara, sonra şampiyon etrafında mutasyon
    adaylar = [(s["xi"], s["reg"])]
    if kayit["nesil"] == 0:
        adaylar += list(itertools.product([0.001, 0.0025, 0.005], [1.0, 3.0, 10.0, 30.0]))
    for _ in range(A.DENEME_SAYISI):
        adaylar.append((float(np.clip(s["xi"] * np.exp(rng.normal(0, 0.4)), 1e-4, 0.02)),
                        float(np.clip(s["reg"] * np.exp(rng.normal(0, 0.5)), 0.1, 200))))
    meydan = degerlendir(oyn, test, adaylar, eloler, ber)

    gelisti = meydan["skor"] < sampiyon["skor"] - 1e-6
    kazanan = meydan if gelisti else sampiyon
    kayit["ayar"] = kazanan["ayar"]
    kayit["nesil"] += 1
    kayit["sinav"] = {k: v for k, v in kazanan.items() if k != "ayar"}
    kayit["sinav"]["mac"] = int(len(test))
    kayit["sinav"].update(referanslar(test))
    r = roi(df, test, kazanan["ayar"], ber)
    if r:
        kayit["sinav"]["roi"] = r
    kayit["gecmis"].append({"tarih": dt.date.today().isoformat(), "nesil": kayit["nesil"],
                            "skor": round(kazanan["skor"], 5), "eski_skor": round(sampiyon["skor"], 5),
                            "gelisti": bool(gelisti), "ayar": kazanan["ayar"]})
    kayit["gecmis"] = kayit["gecmis"][-100:]
    kayit.pop("not", None)
    return kayit
