"""Sayıları Türkçe yazıya çevirir (seslendirme doğru okusun diye)."""

ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]


def _below_1000(n):
    h, r = divmod(n, 100)
    t, o = divmod(r, 10)
    parts = []
    if h:
        parts.append("yüz" if h == 1 else f"{ONES[h]} yüz")
    if t:
        parts.append(TENS[t])
    if o:
        parts.append(ONES[o])
    return " ".join(parts)


def num_to_words(n):
    n = int(n)
    if n == 0:
        return "sıfır"
    parts = []
    for value, name in ((10**9, "milyar"), (10**6, "milyon"), (1000, "bin")):
        q, n = divmod(n, value)
        if q:
            parts.append(name if (q == 1 and name == "bin") else f"{_below_1000(q)} {name}")
    if n:
        parts.append(_below_1000(n))
    return " ".join(parts)


_ORD = {"bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü",
        "beş": "beşinci", "altı": "altıncı", "yedi": "yedinci", "sekiz": "sekizinci",
        "dokuz": "dokuzuncu", "on": "onuncu", "yirmi": "yirminci", "otuz": "otuzuncu",
        "kırk": "kırkıncı", "elli": "ellinci", "altmış": "altmışıncı",
        "yetmiş": "yetmişinci", "seksen": "sekseninci", "doksan": "doksanıncı",
        "yüz": "yüzüncü", "bin": "bininci"}


def ordinal_words(n):
    words = num_to_words(n).split()
    words[-1] = _ORD.get(words[-1], words[-1])
    return " ".join(words)


def decimal_to_words(x, places=2):
    """1.70 -> 'bir virgül yetmiş', 2.05 -> 'iki virgül sıfır beş'."""
    s = f"{x:.{places}f}"
    whole, frac = s.split(".")
    frac = frac.rstrip("0") or "0"
    if len(frac) == 1:
        frac += "0"  # 1.7 -> "yetmiş" (bahis oranı alışkanlığı)
    frac_words = ("sıfır " + num_to_words(int(frac))) if frac.startswith("0") else num_to_words(int(frac))
    return f"{num_to_words(int(whole))} virgül {frac_words}"


if __name__ == "__main__":
    for v in (500, 850, 1445, 2456, 3500):
        print(v, num_to_words(v))
    print(ordinal_words(1), ordinal_words(2), ordinal_words(3))
    print(decimal_to_words(1.70), "|", decimal_to_words(2.05), "|", decimal_to_words(1.85))
