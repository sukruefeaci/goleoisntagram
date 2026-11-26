"""Hafıza: maçtan ÖNCE yapılan tahminleri saklar, sonuçlar gelince karne çıkarır."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import ayarlar as A
from . import model as M

SUTUN = ["anahtar", "lig", "tarih", "ev", "dep", "yapildi", "nesil", "p1", "px", "p2", "pU1.5", "pU2.5",
         "pU3.5", "pKG", "skor", "secim", "secim_p", "eg", "dg", "dogru_1x2", "dogru_ust", "dogru_secim"]


def yukle() -> pd.DataFrame:
    if A.TAHMIN_DOSYA.exists():
        return pd.read_csv(A.TAHMIN_DOSYA)
    return pd.DataFrame(columns=SUTUN)


def kaydet(df: pd.DataFrame):
    A.DURUM.mkdir(parents=True, exist_ok=True)
    df[SUTUN].to_csv(A.TAHMIN_DOSYA, index=False)


def anahtar(lig, tarih, ev, dep):
    return f"{lig}|{pd.Timestamp(tarih).date()}|{ev}|{dep}"


def secim_tuttu(k: str, eg: float, dg: float) -> bool:
    t = eg + dg
    return {"1": eg > dg, "X": eg == dg, "2": eg < dg, "1X": eg >= dg, "X2": eg <= dg, "12": eg != dg,
            "U1.5": t > 1.5, "A1.5": t < 1.5, "U2.5": t > 2.5, "A2.5": t < 2.5, "U3.5": t > 3.5,
            "A3.5": t < 3.5, "KG": eg > 0 and dg > 0, "KGY": not (eg > 0 and dg > 0)}[k]


def tahmin_ekle(h: pd.DataFrame, lig: str, tahminler: pd.DataFrame, nesil: int) -> pd.DataFrame:
    """Henüz oynanmamış maçların tahminini kaydet (maç başlayana kadar en güncel tahmin tutulur)."""
    bugun = pd.Timestamp.now().normalize()
    yeni = []
    for _, r in tahminler.iterrows():
        k, kp = M.en_iyi_secim(r)
        yeni.append({"anahtar": anahtar(lig, r["tarih"], r["ev"], r["dep"]), "lig": lig,
                     "tarih": pd.Timestamp(r["tarih"]).date().isoformat(), "ev": r["ev"], "dep": r["dep"],
                     "yapildi": bugun.date().isoformat(), "nesil": nesil,
                     **{c: round(float(r[c]), 4) for c in ["p1", "px", "p2", "pU1.5", "pU2.5", "pU3.5", "pKG"]},
                     "skor": r["skor"], "secim": k, "secim_p": round(float(kp), 4)})
    if not yeni:
        return h
    yeni = pd.DataFrame(yeni)
    # sonucu henüz gelmemiş eski kaydı yenisiyle değiştir
    eski = h[~(h["anahtar"].isin(yeni["anahtar"]) & h["eg"].isna())]
    yeni = yeni[~yeni["anahtar"].isin(eski["anahtar"])]
    return pd.concat([eski, yeni], ignore_index=True)


def sonuclari_isle(h: pd.DataFrame, lig: str, df: pd.DataFrame) -> int:
    oyn = df[df["eg"].notna()]
    sonuc = {anahtar(lig, t, e, d): (g1, g2) for t, e, d, g1, g2 in
             zip(oyn["tarih"], oyn["ev"], oyn["dep"], oyn["eg"], oyn["dg"])}
    n = 0
    for i in h.index[(h["lig"] == lig) & h["eg"].isna()]:
        if h.at[i, "anahtar"] in sonuc:
            g1, g2 = sonuc[h.at[i, "anahtar"]]
            h.at[i, "eg"], h.at[i, "dg"] = g1, g2
            gercek = 0 if g1 > g2 else 1 if g1 == g2 else 2
            h.at[i, "dogru_1x2"] = int(np.argmax([h.at[i, "p1"], h.at[i, "px"], h.at[i, "p2"]]) == gercek)
            h.at[i, "dogru_ust"] = int((h.at[i, "pU2.5"] > 0.5) == (g1 + g2 > 2.5))
            h.at[i, "dogru_secim"] = int(secim_tuttu(h.at[i, "secim"], g1, g2))
            n += 1
    return n


def karne(h: pd.DataFrame, lig: str | None = None) -> dict:
    d = h[h["eg"].notna()]
    if lig:
        d = d[d["lig"] == lig]
    if not len(d):
        return {"mac": 0}
    d = d.astype({"dogru_1x2": float, "dogru_ust": float, "dogru_secim": float, "secim_p": float})
    return {"mac": len(d), "isabet_1x2": d["dogru_1x2"].mean(), "isabet_ust": d["dogru_ust"].mean(),
            "isabet_secim": d["dogru_secim"].mean(), "beklenen_secim": d["secim_p"].mean()}
