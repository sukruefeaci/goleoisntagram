"""Tahmin motoru: zaman ağırlıklı Dixon-Coles Poisson + Elo, kalibrasyonlu karışım.

Tüm ayarlar (xi, reg, rho, w_elo, K, T) sabit değil; `ogrenme.py` bunları her
güncellemede geçmiş maçlar üzerinde sınayıp en iyisini seçer.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import ayarlar as A

MAX_GOL = 11
_FAKT = np.array([math.factorial(k) for k in range(MAX_GOL)], dtype=float)
YENI_TAKIM = -0.15  # verisi olmayan (yeni çıkan) takım için atak/savunma ön kabulü
ELO_HFA = 60.0


# ---------------------------------------------------------------- Poisson
def poisson_egit(ev, dep, eg, dg, w, n_takim, reg, tur=60):
    """Ağırlıklı, L2 düzenlemeli Poisson regresyonu (blok Newton adımları)."""
    att = np.zeros(n_takim)
    dfn = np.zeros(n_takim)
    ort = max(np.average(np.concatenate([eg, dg]), weights=np.concatenate([w, w])), 0.1)
    mu, ha = math.log(ort), 0.2
    for _ in range(tur):
        lh = np.exp(mu + ha + att[ev] - dfn[dep]); la = np.exp(mu + att[dep] - dfn[ev])
        mu += (w * (eg - lh + dg - la)).sum() / (w * (lh + la)).sum()
        lh = np.exp(mu + ha + att[ev] - dfn[dep]); la = np.exp(mu + att[dep] - dfn[ev])
        ha += (w * (eg - lh)).sum() / (w * lh).sum()
        lh = np.exp(mu + ha + att[ev] - dfn[dep]); la = np.exp(mu + att[dep] - dfn[ev])
        g = np.bincount(ev, w * (eg - lh), n_takim) + np.bincount(dep, w * (dg - la), n_takim) - reg * att
        h = np.bincount(ev, w * lh, n_takim) + np.bincount(dep, w * la, n_takim) + reg
        adim_a = g / h
        att += adim_a
        lh = np.exp(mu + ha + att[ev] - dfn[dep]); la = np.exp(mu + att[dep] - dfn[ev])
        g = -np.bincount(dep, w * (eg - lh), n_takim) - np.bincount(ev, w * (dg - la), n_takim) - reg * dfn
        h = np.bincount(dep, w * lh, n_takim) + np.bincount(ev, w * la, n_takim) + reg
        adim_d = g / h
        dfn += adim_d
        if max(np.abs(adim_a).max(), np.abs(adim_d).max()) < 1e-5:
            break
    return mu, ha, att, dfn


def lambdalar(gecmis: pd.DataFrame, hedef: pd.DataFrame, ref: pd.Timestamp, xi: float, reg: float):
    """`ref` tarihinden önceki maçlarla eğitip `hedef` maçların beklenen gollerini döndür."""
    g = gecmis[(gecmis["tarih"] < ref) & gecmis["eg"].notna()]
    gun = (ref - g["tarih"]).dt.days.to_numpy()
    g = g[gun <= A.EGITIM_GUN]; gun = gun[gun <= A.EGITIM_GUN]
    takimlar = pd.Index(pd.unique(pd.concat([g["ev"], g["dep"]])))
    n = len(takimlar)
    if len(g) < 30:
        return np.full(len(hedef), 1.45), np.full(len(hedef), 1.15)
    mu, ha, att, dfn = poisson_egit(takimlar.get_indexer(g["ev"]), takimlar.get_indexer(g["dep"]),
                                    g["eg"].to_numpy(float), g["dg"].to_numpy(float),
                                    np.exp(-xi * gun), n, reg)
    att = np.append(att, YENI_TAKIM); dfn = np.append(dfn, YENI_TAKIM)  # son indeks = yeni takım
    i = takimlar.get_indexer(hedef["ev"]); j = takimlar.get_indexer(hedef["dep"])
    i[i < 0] = n; j[j < 0] = n
    return np.exp(mu + ha + att[i] - dfn[j]), np.exp(mu + att[j] - dfn[i])


def skor_matrisi(lh, la, rho):
    """P[n, ev_gol, dep_gol] — Dixon-Coles düşük skor düzeltmeli."""
    k = np.arange(MAX_GOL)
    ph = np.exp(-lh[:, None]) * lh[:, None] ** k / _FAKT
    pa = np.exp(-la[:, None]) * la[:, None] ** k / _FAKT
    P = ph[:, :, None] * pa[:, None, :]
    P[:, 0, 0] *= np.clip(1 - lh * la * rho, 0, None)
    P[:, 0, 1] *= np.clip(1 + lh * rho, 0, None)
    P[:, 1, 0] *= np.clip(1 + la * rho, 0, None)
    P[:, 1, 1] *= max(1 - rho, 0)
    return P / P.sum(axis=(1, 2), keepdims=True)


_I, _J = np.meshgrid(np.arange(MAX_GOL), np.arange(MAX_GOL), indexing="ij")


def pazarlar(P):
    return {
        "1": (P * (_I > _J)).sum((1, 2)), "X": (P * (_I == _J)).sum((1, 2)), "2": (P * (_I < _J)).sum((1, 2)),
        "U1.5": (P * (_I + _J > 1)).sum((1, 2)), "U2.5": (P * (_I + _J > 2)).sum((1, 2)),
        "U3.5": (P * (_I + _J > 3)).sum((1, 2)), "KG": (P * ((_I > 0) & (_J > 0))).sum((1, 2)),
    }


# ---------------------------------------------------------------- Elo
def elo_gecir(df: pd.DataFrame, K: float):
    """Maçları sırayla oynatır. Her maç için maç öncesi Elo farkını ve son puanları döndürür."""
    puan: dict[str, float] = {}
    ilk_tarih = df["tarih"].min() if len(df) else None
    fark = np.full(len(df), np.nan)
    for n, (t, e, d, g1, g2) in enumerate(zip(df["tarih"], df["ev"], df["dep"], df["eg"], df["dg"])):
        for takim in (e, d):
            if takim not in puan:  # ilk sezondan sonra gelen takım = yeni çıkan, biraz zayıf başlar
                puan[takim] = 1500.0 if (t - ilk_tarih).days < 120 else 1450.0
        fark[n] = puan[e] + ELO_HFA - puan[d]
        if np.isnan(g1):
            continue
        beklenen = 1 / (1 + 10 ** (-fark[n] / 400))
        sonuc = 1.0 if g1 > g2 else 0.5 if g1 == g2 else 0.0
        gf = abs(g1 - g2)
        carpan = 1.0 if gf <= 1 else 1.5 if gf == 2 else (11 + gf) / 8
        degisim = K * carpan * (sonuc - beklenen)
        puan[e] += degisim; puan[d] -= degisim
    return fark, puan


def elo_1x2(fark, beraberlik):
    p_ev = 1 / (1 + 10 ** (-fark / 400))
    x = beraberlik * np.exp(-(fark / 600) ** 2)
    return (1 - x) * p_ev, x, (1 - x) * (1 - p_ev)


def karistir(m, fark, beraberlik, w_elo, T):
    """Poisson 1X2 ile Elo 1X2'yi karıştır, sıcaklık (T) ile kalibre et."""
    e1, ex, e2 = elo_1x2(fark, beraberlik)
    p = np.stack([(1 - w_elo) * m["1"] + w_elo * e1, (1 - w_elo) * m["X"] + w_elo * ex,
                  (1 - w_elo) * m["2"] + w_elo * e2], axis=1)
    p = np.clip(p, 1e-9, 1) ** (1 / T)
    return p / p.sum(axis=1, keepdims=True)


def beraberlik_orani(df):
    o = df[df["eg"].notna()]
    if len(o) < 50:
        return 0.27
    return float((o["eg"] == o["dg"]).mean()) * 1.08  # elo_1x2 ortalamada ~%8 kırptığı için


# ---------------------------------------------------------------- canlı tahmin
def tahmin_et(df: pd.DataFrame, hedef: pd.DataFrame, p: dict) -> pd.DataFrame:
    """`hedef` (ev, dep sütunlu) maçları için tüm pazar olasılıklarını hesapla."""
    ref = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
    lh, la = lambdalar(df, hedef, ref, p["xi"], p["reg"])
    P = skor_matrisi(lh, la, p["rho"])
    m = pazarlar(P)
    _, puan = elo_gecir(df[df["eg"].notna()], p["K"])
    fark = np.array([puan.get(e, 1450.0) + ELO_HFA - puan.get(d, 1450.0) for e, d in zip(hedef["ev"], hedef["dep"])])
    p3 = karistir(m, fark, beraberlik_orani(df), p["w_elo"], p["T"])
    out = hedef.copy().reset_index(drop=True)
    out["xg_ev"], out["xg_dep"] = lh, la
    out["p1"], out["px"], out["p2"] = p3[:, 0], p3[:, 1], p3[:, 2]
    for k in ["U1.5", "U2.5", "U3.5", "KG"]:
        out["p" + k] = m[k]
    enc = P.reshape(len(P), -1).argmax(1)
    out["skor"] = [f"{s // MAX_GOL}-{s % MAX_GOL}" for s in enc]
    return out


ETIKET = {"1": "MS 1", "X": "MS X", "2": "MS 2", "1X": "ÇŞ 1X", "X2": "ÇŞ X2", "12": "ÇŞ 12",
          "U1.5": "1.5 Üst", "A1.5": "1.5 Alt", "U2.5": "2.5 Üst", "A2.5": "2.5 Alt",
          "U3.5": "3.5 Üst", "A3.5": "3.5 Alt", "KG": "KG Var", "KGY": "KG Yok"}


def secenekler(r) -> dict[str, float]:
    s = {"1": r["p1"], "X": r["px"], "2": r["p2"], "1X": r["p1"] + r["px"], "X2": r["px"] + r["p2"],
         "12": r["p1"] + r["p2"]}
    for k in ["1.5", "2.5", "3.5"]:
        s["U" + k] = r["pU" + k]; s["A" + k] = 1 - r["pU" + k]
    s["KG"] = r["pKG"]; s["KGY"] = 1 - r["pKG"]
    return s


def en_iyi_secim(r, alt=0.55, ust=0.80):
    """Olasılığı 'oynanabilir' bantta (çok düşük orana düşmeyen) en güçlü seçenek."""
    s = secenekler(r)
    aday = {k: v for k, v in s.items() if alt <= v <= ust and k != "12"}
    if not aday:
        k = max(s, key=s.get)
        return k, s[k]
    k = max(aday, key=aday.get)
    return k, aday[k]
