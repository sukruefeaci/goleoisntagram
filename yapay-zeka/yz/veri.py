"""Ücretsiz veri kaynakları: football-data.co.uk (oranlı) ve openfootball (GitHub).

Bir lig için tek kaynak kullanılır (takım adları kaynaktan kaynağa değiştiği için).
Önce football-data denenir; ulaşılamazsa openfootball'a düşülür.
Elle eklenen sonuçlar (durum/elle_sonuclar.csv) her zaman eklenir.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import urllib.request

import numpy as np
import pandas as pd

from . import ayarlar as A

SUTUNLAR = ["lig", "tarih", "ev", "dep", "eg", "dg", "o1", "ox", "o2", "oust", "oalt"]


def _indir(url: str, dosya: str, kalici: bool) -> bytes | None:
    """URL'yi indir; başarısız olursa önbellekteki kopyayı döndür."""
    yol = A.ONBELLEK / dosya
    if kalici and yol.exists():
        return yol.read_bytes()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "goleo-yz/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            veri = r.read()
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(veri)
        return veri
    except Exception:
        return yol.read_bytes() if yol.exists() else None


def sezonlar(bugun: dt.date | None = None) -> list[int]:
    bugun = bugun or dt.date.today()
    simdiki = bugun.year if bugun.month >= 7 else bugun.year - 1
    return list(range(simdiki - A.SEZON_SAYISI + 1, simdiki + 1))


# ---------------------------------------------------------------- football-data
def _fd_oku(ham: bytes, lig: str) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(ham), encoding="latin-1", on_bad_lines="skip")
    if "HomeTeam" not in df.columns and "Home" in df.columns:
        df = df.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG"})
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "Date"])

    def ilk(*adlar):
        for a in adlar:
            if a in df.columns:
                return pd.to_numeric(df[a], errors="coerce")
        return np.nan

    return pd.DataFrame({
        "lig": lig,
        "tarih": pd.to_datetime(df["Date"], dayfirst=True, errors="coerce"),
        "ev": df["HomeTeam"].astype(str).str.strip(),
        "dep": df["AwayTeam"].astype(str).str.strip(),
        "eg": ilk("FTHG"), "dg": ilk("FTAG"),
        "o1": ilk("AvgH", "BbAvH", "B365H"), "ox": ilk("AvgD", "BbAvD", "B365D"),
        "o2": ilk("AvgA", "BbAvA", "B365A"),
        "oust": ilk("Avg>2.5", "BbAv>2.5", "B365>2.5"), "oalt": ilk("Avg<2.5", "BbAv<2.5", "B365<2.5"),
    })


def _fd_lig(lig: str) -> pd.DataFrame | None:
    kod = A.LIGLER[lig][2]
    parcalar = []
    ss = sezonlar()
    for y in ss:
        s = f"{y % 100:02d}{(y + 1) % 100:02d}"
        ham = _indir(f"https://www.football-data.co.uk/mmz4281/{s}/{kod}.csv",
                     f"fd_{s}_{kod}.csv", kalici=(y != ss[-1]))
        if ham is None:
            if y == ss[-1]:
                return None  # güncel sezon yoksa bu kaynak işe yaramaz
            continue
        parcalar.append(_fd_oku(ham, lig))
    ham = _indir("https://www.football-data.co.uk/fixtures.csv", "fd_fixtures.csv", kalici=False)
    if ham is not None:
        fx = pd.read_csv(io.BytesIO(ham), encoding="latin-1", on_bad_lines="skip")
        fx.columns = [c.lstrip("﻿ï»¿") for c in fx.columns]
        if "Div" in fx.columns:
            fx = fx[fx["Div"] == kod]
            if len(fx):
                f = _fd_oku(fx.to_csv(index=False).encode("latin-1", "replace"), lig)
                f["eg"] = np.nan
                f["dg"] = np.nan
                parcalar.append(f)
    return pd.concat(parcalar, ignore_index=True) if parcalar else None


# ---------------------------------------------------------------- openfootball
def _of_lig(lig: str) -> pd.DataFrame | None:
    dosya = A.LIGLER[lig][1]
    satirlar = []
    ss = sezonlar()
    for y in ss:
        s = f"{y}-{(y + 1) % 100:02d}"
        ham = _indir(f"https://raw.githubusercontent.com/openfootball/football.json/master/{s}/{dosya}.json",
                     f"of_{s}_{dosya}.json", kalici=(y < ss[-1] - 1))
        if ham is None:
            continue
        try:
            d = json.loads(ham)
        except ValueError:
            continue
        maclar = d.get("matches") or [m for r in d.get("rounds", []) for m in r.get("matches", [])]
        for m in maclar:
            sk = m.get("score")
            ft = sk.get("ft") if isinstance(sk, dict) else (sk if isinstance(sk, list) else None)
            if ft is None and "score1" in m:
                ft = [m.get("score1"), m.get("score2")]
            eg, dg = (ft if ft and len(ft) == 2 and None not in ft else (np.nan, np.nan))
            satirlar.append({"lig": lig, "tarih": pd.to_datetime(m.get("date"), errors="coerce"),
                             "ev": str(m.get("team1", "")).strip(), "dep": str(m.get("team2", "")).strip(),
                             "eg": eg, "dg": dg})
    if not satirlar:
        return None
    df = pd.DataFrame(satirlar)
    for c in ["o1", "ox", "o2", "oust", "oalt"]:
        df[c] = np.nan
    return df


# ---------------------------------------------------------------- elle eklenenler
def elle_oku() -> pd.DataFrame:
    if not A.ELLE_DOSYA.exists():
        return pd.DataFrame(columns=SUTUNLAR)
    df = pd.read_csv(A.ELLE_DOSYA)
    df["tarih"] = pd.to_datetime(df["tarih"], errors="coerce")
    for c in SUTUNLAR:
        if c not in df.columns:
            df[c] = np.nan
    return df[SUTUNLAR]


def elle_ekle(lig, tarih, ev, dep, eg, dg):
    yeni = pd.DataFrame([{"lig": lig, "tarih": tarih, "ev": ev, "dep": dep, "eg": eg, "dg": dg}])
    if A.ELLE_DOSYA.exists():
        yeni = pd.concat([pd.read_csv(A.ELLE_DOSYA), yeni], ignore_index=True)
    A.DURUM.mkdir(parents=True, exist_ok=True)
    yeni.to_csv(A.ELLE_DOSYA, index=False)


# ---------------------------------------------------------------- ana giriş
def lig_verisi(lig: str) -> tuple[pd.DataFrame, str]:
    df, kaynak = _fd_lig(lig), "football-data.co.uk"
    if df is None or df["eg"].notna().sum() < 200:
        df, kaynak = _of_lig(lig), "openfootball"
    if df is None:
        df, kaynak = pd.DataFrame(columns=SUTUNLAR), "yok"
    elle = elle_oku()
    elle = elle[elle["lig"] == lig]
    if len(elle):
        df = pd.concat([df[SUTUNLAR], elle], ignore_index=True)
    df = df.dropna(subset=["tarih"])
    df = df[(df["ev"] != "") & (df["dep"] != "")]
    # aynı maç birden çok kez geldiyse (fikstür + sonuç, elle + kaynak) sonuçlu olanı tut
    df["_gun"] = df["tarih"].dt.normalize()
    df = (df.sort_values("eg", na_position="first")
            .drop_duplicates(subset=["_gun", "ev", "dep"], keep="last")
            .drop(columns="_gun").sort_values("tarih").reset_index(drop=True))
    for c in ["eg", "dg", "o1", "ox", "o2", "oust", "oalt"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[SUTUNLAR], kaynak
