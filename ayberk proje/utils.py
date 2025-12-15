"""
utils.py

Bu dosya, uygulamanin is mantigini icerir:
- Veri hazirlama (dataset.xlsx okuma ve standart sutunlara donusturme)
- AHP (kriter agirliklari ve tutarlilik)
- TOPSIS (puan hesaplama)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# AHP icin Rastgele Indeks (RI) tablosu (n <= 10)
# ---------------------------------------------------------------------------
RASTGELE_INDEKS_TABLOSU: dict[int, float] = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
    10: 1.49,
}


@dataclass(frozen=True)
class AHPHesapSonucu:
    """
    AHP hesap ciktilari.

    - agirliklar: Kriter agirliklari (toplami 1 olacak sekilde)
    - lambda_maks: En buyuk ozdeger
    - ci: Consistency Index
    - cr: Consistency Ratio
    """

    agirliklar: pd.Series
    lambda_maks: float
    ci: float
    cr: float


# ---------------------------------------------------------------------------
# Veri hazirlama (yerel dataset.xlsx)
# ---------------------------------------------------------------------------


def verisetini_yukle_ve_hazirla_xlsx(dosya_yolu: Path) -> pd.DataFrame:
    """
    `dataset.xlsx` dosyasini okur ve uygulamanin kullanacagi sutunlara donusturur.

    Cikti sutunlari:
    - marka, model, yil (varsa)
    - yakit_tipi: elektrik/hibrit/benzin/dizel
    - beygir_gucu
    - kapi_sayisi
    - kasa_tipi: hb/sedan/suv/kupe
    """

    if not dosya_yolu.exists():
        raise FileNotFoundError(f"Veri dosyasi bulunamadi: {dosya_yolu}")

    ham = pd.read_excel(dosya_yolu)

    gerekli_sutunlar = {
        "Make": "marka",
        "Model": "model",
        "Year": "yil",
        "Engine Fuel Type": "yakit_ham",
        "Engine HP": "beygir_gucu",
        "Number of Doors": "kapi_sayisi",
        "Vehicle Style": "kasa_ham",
    }

    eksik = [s for s in gerekli_sutunlar.keys() if s not in ham.columns]
    if eksik:
        raise ValueError(f"Veri setinde gerekli sutunlar eksik: {', '.join(eksik)}")

    veri = ham[list(gerekli_sutunlar.keys())].rename(columns=gerekli_sutunlar).copy()

    veri["yakit_tipi"] = veri["yakit_ham"].apply(_yakit_tipini_standartlastir)
    veri["kasa_tipi"] = veri["kasa_ham"].apply(_kasa_tipini_standartlastir)

    veri["beygir_gucu"] = veri["beygir_gucu"].apply(_float_cevir)
    veri["kapi_sayisi"] = veri["kapi_sayisi"].apply(_int_cevir)

    sutunlar = ["marka", "model", "yil", "yakit_tipi", "beygir_gucu", "kapi_sayisi", "kasa_tipi"]
    veri = veri[sutunlar].dropna(subset=["yakit_tipi", "kasa_tipi", "beygir_gucu", "kapi_sayisi"])

    veri["beygir_gucu"] = veri["beygir_gucu"].astype(float)
    veri["kapi_sayisi"] = veri["kapi_sayisi"].astype(int)
    veri["yil"] = veri["yil"].astype(int)

    return veri.reset_index(drop=True)


def _yakit_tipini_standartlastir(deger: Any) -> str | None:
    """
    Yakit bilgisini 4 ana sinifa indirger:
    - elektrik, hibrit, benzin, dizel
    """

    if deger is None or (isinstance(deger, float) and np.isnan(deger)):
        return None

    metin = str(deger).strip().lower()

    if "electric" in metin:
        return "elektrik"
    if "hybrid" in metin:
        return "hibrit"
    if "diesel" in metin:
        return "dizel"

    # Bu veri setinde benzin genelde "unleaded" veya "gasoline" gibi ifadelerle geciyor.
    if any(kelime in metin for kelime in ["unleaded", "gasoline", "flex-fuel", "e85", "ethanol", "gas"]):
        return "benzin"

    return None


def _kasa_tipini_standartlastir(deger: Any) -> str | None:
    """
    Kasa bilgisini 4 ana sinifa indirger:
    - hb, sedan, suv, kupe
    """

    if deger is None or (isinstance(deger, float) and np.isnan(deger)):
        return None

    metin = str(deger).strip().lower()

    if "suv" in metin or "crossover" in metin:
        return "suv"
    if "hatch" in metin:
        return "hb"
    if "sedan" in metin:
        return "sedan"
    if "coupe" in metin:
        return "kupe"

    return None


def _float_cevir(deger: Any) -> float | None:
    """Gelen degeri guvenli sekilde float'a cevirir; olmazsa None doner."""

    if deger is None or (isinstance(deger, float) and np.isnan(deger)):
        return None
    try:
        return float(deger)
    except Exception:
        return None


def _int_cevir(deger: Any) -> int | None:
    """Gelen degeri guvenli sekilde int'e cevirir; olmazsa None doner."""

    sayi = _float_cevir(deger)
    if sayi is None:
        return None
    try:
        return int(round(sayi))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AHP
# ---------------------------------------------------------------------------


def ikili_karsilastirma_matrisi_dogrula(matris: np.ndarray, *, tolerans: float = 1e-8) -> list[str]:
    """
    AHP ikili karsilastirma matrisi dogrulamasi.

    Kurallar:
    - Kare matris (n x n)
    - Pozitif ve sonlu sayilar
    - Kosegen degerleri 1
    - Karsiliklilik: a_ij = 1 / a_ji
    """

    hatalar: list[str] = []

    if matris.ndim != 2 or matris.shape[0] != matris.shape[1]:
        return ["Ikili karsilastirma matrisi kare olmali (n x n)."]

    if not np.isfinite(matris).all() or np.any(matris <= 0):
        hatalar.append("Tum hucreler pozitif ve sonlu sayilar olmali.")

    if not np.allclose(np.diag(matris), 1.0, atol=tolerans):
        hatalar.append("Kosegen degerleri 1 olmali.")

    karsilik = np.reciprocal(matris, where=matris != 0)
    if not np.allclose(matris.T, karsilik, atol=1e-6):
        hatalar.append("Matris karsilikli olmali: a_ij = 1 / a_ji.")

    return hatalar


def ahp_agirliklarini_hesapla(ikili_matris: np.ndarray, kriterler: Sequence[str]) -> AHPHesapSonucu:
    """
    AHP agirliklarini en buyuk ozvektor yontemi ile hesaplar.

    Ozet:
    1) Ozdeger/ozvektorleri bul
    2) En buyuk ozdegerin ozvektorunu al
    3) Ozvektoru normalize et (toplam 1) -> agirliklar
    4) CI ve CR hesapla
    """

    matris = np.asarray(ikili_matris, dtype=float)
    if matris.shape[0] != len(kriterler):
        raise ValueError("Kriter sayisi ile matris boyutu uyusmuyor.")

    hatalar = ikili_karsilastirma_matrisi_dogrula(matris)
    if hatalar:
        raise ValueError("Gecersiz ikili karsilastirma matrisi: " + "; ".join(hatalar))

    ozdegerler, ozvektorler = np.linalg.eig(matris)
    indeks = int(np.argmax(ozdegerler.real))

    lambda_maks = float(ozdegerler.real[indeks])
    ana_ozvektor = np.abs(ozvektorler[:, indeks].real)
    agirliklar = ana_ozvektor / ana_ozvektor.sum()

    n = matris.shape[0]
    ci = float((lambda_maks - n) / (n - 1)) if n > 1 else 0.0
    ri = RASTGELE_INDEKS_TABLOSU.get(n, 0.0)
    cr = float(ci / ri) if ri > 0 else 0.0

    # Kayan nokta hatalari nedeniyle -0.0 gibi degerleri temizle.
    ci = max(ci, 0.0)
    cr = max(cr, 0.0)

    return AHPHesapSonucu(
        agirliklar=pd.Series(agirliklar, index=list(kriterler), name="agirlik"),
        lambda_maks=lambda_maks,
        ci=ci,
        cr=cr,
    )


# ---------------------------------------------------------------------------
# TOPSIS
# ---------------------------------------------------------------------------


def kullanici_maliyet_matrisi_olustur(
    araclar: pd.DataFrame,
    *,
    kullanici_yakit_tipi: str,
    kullanici_beygir_gucu: float,
    kullanici_kapi_sayisi: int,
    kullanici_kasa_tipi: str,
    yakit_puanlari: Mapping[str, float],
    kasa_puanlari: Mapping[str, float],
) -> pd.DataFrame:
    """
    TOPSIS karar matrisini "maliyet" mantigi ile olusturur (dusuk daha iyi).

    Bu projede hedef, kullanicinin istedigi degerlere "en yakin" araci bulmaktir.
    Bu nedenle her kriteri bir "mesafe" olarak tanimlariz.
    """

    if kullanici_yakit_tipi not in yakit_puanlari:
        raise ValueError(f"Bilinmeyen yakit_tipi: {kullanici_yakit_tipi}")
    if kullanici_kasa_tipi not in kasa_puanlari:
        raise ValueError(f"Bilinmeyen kasa_tipi: {kullanici_kasa_tipi}")

    yakit_hedef = float(yakit_puanlari[kullanici_yakit_tipi])
    kasa_hedef = float(kasa_puanlari[kullanici_kasa_tipi])

    karar = pd.DataFrame(index=araclar.index)
    karar["yakit_tipi"] = araclar["yakit_tipi"].map(yakit_puanlari).astype(float).sub(yakit_hedef).abs()
    karar["beygir_gucu"] = (araclar["beygir_gucu"].astype(float) - float(kullanici_beygir_gucu)).abs()
    karar["kapi_sayisi"] = (araclar["kapi_sayisi"].astype(int) - int(kullanici_kapi_sayisi)).abs().astype(float)
    karar["kasa_tipi"] = araclar["kasa_tipi"].map(kasa_puanlari).astype(float).sub(kasa_hedef).abs()
    return karar


def topsis_puanlarini_hesapla(
    karar_matrisi: pd.DataFrame,
    *,
    agirliklar: Mapping[str, float],
    yonler: Mapping[str, Literal["fayda", "maliyet"]],
) -> pd.Series:
    """
    TOPSIS puani hesaplar.

    Adimlar:
    1) Vektor normu ile normalize et
    2) Agirliklari uygula
    3) Ideal / anti-ideal noktalarini bul
    4) Uzakliklari hesapla (D+ ve D-)
    5) Puan = D- / (D+ + D-)
    """

    if karar_matrisi.empty:
        raise ValueError("Karar matrisi bos olamaz.")

    matris = karar_matrisi.astype(float).to_numpy(copy=True)
    if not np.isfinite(matris).all():
        raise ValueError("Karar matrisinde gecersiz (sonlu olmayan) deger var.")

    sutunlar = list(karar_matrisi.columns)

    w = np.array([float(agirliklar[s]) for s in sutunlar], dtype=float)
    if np.any(w < 0) or not np.isfinite(w).all():
        raise ValueError("Agirliklar pozitif ve sonlu olmalidir.")

    w_toplam = float(w.sum())
    if w_toplam <= 0:
        raise ValueError("Agirliklarin toplami 0'dan buyuk olmali.")
    w = w / w_toplam

    yon_listesi = [yonler[s] for s in sutunlar]
    if any(y not in ("fayda", "maliyet") for y in yon_listesi):
        raise ValueError("Yonler 'fayda' veya 'maliyet' olmalidir.")

    # 1) Normalize
    payda = np.sqrt(np.sum(matris**2, axis=0))
    payda = np.where(payda == 0, 1.0, payda)
    normalize = matris / payda

    # 2) Agirlik uygula
    agirlikli = normalize * w

    # 3) Ideal / anti-ideal
    ideal = np.empty(agirlikli.shape[1], dtype=float)
    anti = np.empty(agirlikli.shape[1], dtype=float)
    for j, yon in enumerate(yon_listesi):
        if yon == "fayda":
            ideal[j] = float(np.max(agirlikli[:, j]))
            anti[j] = float(np.min(agirlikli[:, j]))
        else:  # maliyet
            ideal[j] = float(np.min(agirlikli[:, j]))
            anti[j] = float(np.max(agirlikli[:, j]))

    # 4) Uzakliklar
    d_arti = np.sqrt(np.sum((agirlikli - ideal) ** 2, axis=1))
    d_eksi = np.sqrt(np.sum((agirlikli - anti) ** 2, axis=1))

    # 5) Puan
    payda = d_arti + d_eksi
    puan = np.where(payda == 0, 0.0, d_eksi / payda)

    return pd.Series(puan, index=karar_matrisi.index, name="topsis_puani")
