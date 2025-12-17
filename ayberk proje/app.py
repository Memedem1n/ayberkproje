"""
app.py

Bu uygulama, kullanicinin tercihleri icin:
- AHP ile kriter agirliklarini hesaplar
- TOPSIS ile araclari siralar ve onerir

Sadelik hedefi:
- Veri kaynagi olarak sadece klasordeki `dataset.xlsx` kullanilir.
- Kod, okunabilir ve parcalara ayrilmis sekilde tutulur.

Calistirma notu:
- Bu dosya Streamlit ile calisir. En kolay yol: `python calistir.py`
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import utils


# ---------------------------------------------------------------------------
# Dogrudan calistirma destegi
# ---------------------------------------------------------------------------
# Aciklama:
# - Streamlit uygulamalari normalde `streamlit run app.py` ile calistirilir.
# - Bazi IDE'lerde Run tusu `python app.py` calistirdigi icin, burada otomatik yonlendirme yapiyoruz.
# - Streamlit icinde calisirken bu blok devreye girmez.


def streamlit_icinde_mi() -> bool:
    """Kod Streamlit tarafindan mi calistiriliyor?"""

    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


if __name__ == "__main__" and not streamlit_icinde_mi():
    import subprocess
    import sys

    proje = Path(__file__).resolve().parent
    komut = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(Path(__file__).resolve()),
        "--browser.gatherUsageStats",
        "false",
    ]
    raise SystemExit(subprocess.call(komut, cwd=str(proje)))


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

UYGULAMA_BASLIGI = "AHP + TOPSIS Tabanli Arac Oneri Uygulamasi"
VERI_DOSYASI_YOLU = Path(__file__).parent / "dataset.xlsx"

CR_ESIGI = 0.10

KRITERLER = ["yakit_tipi", "beygir_gucu", "kapi_sayisi", "kasa_tipi"]

KRITER_ETIKETLERI: dict[str, str] = {
    "yakit_tipi": "yakit tipi",
    "beygir_gucu": "beygir gucu",
    "kapi_sayisi": "kapi sayisi",
    "kasa_tipi": "kasa tipi",
}

VARSAYILAN_YAKIT_PUANLARI: dict[str, float] = {"elektrik": 5, "hibrit": 4, "benzin": 3, "dizel": 2}
VARSAYILAN_KASA_PUANLARI: dict[str, float] = {"hb": 3, "sedan": 2, "suv": 4, "kupe": 3}

TOPSIS_YONLERI = {kriter: "maliyet" for kriter in KRITERLER}


# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------

def arac_etiketi(satir: pd.Series) -> str:
    """
    Tablo ve sonuc ekraninda arac ismini tek satirda gostermek icin kullanilir.
    """

    marka = str(satir.get("marka", "")).strip()
    model = str(satir.get("model", "")).strip()
    yil = satir.get("yil")

    if pd.notna(yil):
        return f"{marka} {model} ({int(yil)})".strip()
    return f"{marka} {model}".strip() if (marka or model) else f"Arac #{int(satir.name) + 1}"


@st.cache_data(show_spinner=False)
def verisetini_yukle() -> pd.DataFrame:
    """
    Streamlit her etkileisimde kodu bastan calistirdigi icin,
    veriyi onbellege almak uygulamayi hizlandirir.
    """

    return utils.verisetini_yukle_ve_hazirla_xlsx(VERI_DOSYASI_YOLU)


def puanlari_duzenle(baslik: str, puanlar: dict[str, float], *, anahtar: str) -> dict[str, float]:
    """
    Kenar cubukta kategori puanlarini basit bir tabloda duzenletebilmek icin kullanilir.
    """

    st.sidebar.subheader(baslik)
    tablo = pd.DataFrame({"kategori": list(puanlar.keys()), "puan": list(puanlar.values())})
    duzenlenmis = st.sidebar.data_editor(
        tablo,
        hide_index=True,
        disabled=["kategori"],
        key=anahtar,
        column_config={"puan": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.3f")},
    )
    return {str(satir["kategori"]): float(satir["puan"]) for _, satir in duzenlenmis.iterrows()}


# ---------------------------------------------------------------------------
# Arayuz
# ---------------------------------------------------------------------------

st.set_page_config(page_title=UYGULAMA_BASLIGI, layout="wide")
st.title(UYGULAMA_BASLIGI)
st.caption("AHP ile kriter agirliklarini hesaplar, TOPSIS ile araclari siralar.")


# 1) Veri seti
st.subheader("1) Veri Seti")
with st.spinner("Veri seti yukleniyor..."):
    try:
        araclar_df = verisetini_yukle()
    except Exception as hata:
        st.error(f"Veri seti yuklenemedi: {hata}")
        st.stop()

st.write(f"Kayit sayisi: {len(araclar_df):,}")
st.dataframe(araclar_df.head(20), use_container_width=True)


# 2) Kategori puanlari (sidebar)
st.sidebar.header("Kategori Puanlari")
st.sidebar.caption("Kategorik degerleri sayisala cevirmek icin kullanilir.")

yakit_puanlari = puanlari_duzenle("Yakit puanlari", VARSAYILAN_YAKIT_PUANLARI, anahtar="yakit_puanlari_duzenleyici")
kasa_puanlari = puanlari_duzenle("Kasa puanlari", VARSAYILAN_KASA_PUANLARI, anahtar="kasa_puanlari_duzenleyici")

if any(v < 0 for v in yakit_puanlari.values()) or any(v < 0 for v in kasa_puanlari.values()):
    st.sidebar.error("Puanlar 0 veya daha buyuk olmali.")


# 3) Kullanici tercihleri
st.subheader("2) Kullanici Tercihleri")

with st.form("kullanici_tercih_formu"):
    s1, s2, s3 = st.columns(3)
    with s1:
        secili_yakit = st.selectbox("Yakit tipi", options=list(yakit_puanlari.keys()), index=2)
    with s2:
        secili_beygir = st.number_input("Beygir gucu", min_value=0.0, max_value=2500.0, value=150.0, step=5.0)
        secili_kapi = st.selectbox("Kapi sayisi", options=[2, 3, 4, 5], index=2)
    with s3:
        secili_kasa = st.radio("Kasa tipi", options=list(kasa_puanlari.keys()), horizontal=True, index=1)

    tercihleri_kaydet = st.form_submit_button("Tercihleri Kaydet")

if tercihleri_kaydet:
    st.session_state["kullanici_tercihleri"] = {
        "yakit_tipi": secili_yakit,
        "beygir_gucu": float(secili_beygir),
        "kapi_sayisi": int(secili_kapi),
        "kasa_tipi": secili_kasa,
    }

kullanici_tercihleri = st.session_state.get("kullanici_tercihleri")
if not kullanici_tercihleri:
    st.info("Devam etmek icin kullanici tercihlerini kaydedin.")
    st.stop()


# 4) AHP ve TOPSIS (Otomatik)
st.subheader("3) AHP ve TOPSIS (Otomatik)")
st.write("Kriterlerin tamami es agirlikli olarak AHP hesaplanir; TOPSIS siralamasi otomatik yapilir.")

try:
    varsayilan_matris = np.ones((len(KRITERLER), len(KRITERLER)), dtype=float)
    ahp_sonuc = utils.ahp_agirliklarini_hesapla(varsayilan_matris, KRITERLER)
    st.session_state["ahp_sonuc"] = ahp_sonuc

    sol, sag = st.columns([2, 1])
    with sol:
        st.write("**Agirliklar**")
        st.dataframe(ahp_sonuc.agirliklar.to_frame(), use_container_width=True)
        st.bar_chart(ahp_sonuc.agirliklar, use_container_width=True)

    with sag:
        st.write("**Tutarlilik**")
        st.metric("Lambda maks", f"{ahp_sonuc.lambda_maks:.4f}")
        st.metric("CI", f"{ahp_sonuc.ci:.4f}")
        st.metric("CR", f"{ahp_sonuc.cr:.4f}")

    karar = utils.kullanici_maliyet_matrisi_olustur(
        araclar_df,
        kullanici_yakit_tipi=kullanici_tercihleri["yakit_tipi"],
        kullanici_beygir_gucu=kullanici_tercihleri["beygir_gucu"],
        kullanici_kapi_sayisi=kullanici_tercihleri["kapi_sayisi"],
        kullanici_kasa_tipi=kullanici_tercihleri["kasa_tipi"],
        yakit_puanlari=yakit_puanlari,
        kasa_puanlari=kasa_puanlari,
    )

    puanlar = utils.topsis_puanlarini_hesapla(
        karar,
        agirliklar=ahp_sonuc.agirliklar.to_dict(),
        yonler=TOPSIS_YONLERI,
    )

    sirali = araclar_df.copy()
    sirali["topsis_puani"] = puanlar
    sirali = sirali.sort_values("topsis_puani", ascending=False).reset_index(drop=True)
    sirali["sira"] = np.arange(1, len(sirali) + 1)
    st.session_state["sirali_df"] = sirali
    st.success("TOPSIS siralamasi tamamlandi.")
except Exception as hata:
    st.error(f"Hesaplama hatasi: {hata}")
    st.stop()

sirali_df: pd.DataFrame | None = st.session_state.get("sirali_df")
if sirali_df is None:
    st.error("Sirali sonuclar olusturulamadi.")
    st.stop()


# 6) Sonuclar + disari aktar
st.subheader("5) Sonuclar")

en_iyi3 = sirali_df.head(3).copy()
en_iyi3["arac"] = en_iyi3.apply(arac_etiketi, axis=1)
st.dataframe(
    en_iyi3[["sira", "arac", "yakit_tipi", "beygir_gucu", "kapi_sayisi", "kasa_tipi", "topsis_puani"]],
    use_container_width=True,
)

st.write("**TOPSIS puanlari (ilk 10)**")
en_iyi10 = sirali_df.head(10).copy()
en_iyi10["arac"] = en_iyi10.apply(arac_etiketi, axis=1)
st.bar_chart(en_iyi10.set_index("arac")["topsis_puani"], use_container_width=True)

en_iyi = sirali_df.iloc[0]
alt1 = sirali_df.iloc[1] if len(sirali_df) > 1 else None
alt2 = sirali_df.iloc[2] if len(sirali_df) > 2 else None


def arac_satiri(satir: pd.Series) -> str:
    return f"{arac_etiketi(satir)} (puan={float(satir['topsis_puani']):.4f})"


st.markdown(f"**En iyi oneri:** {arac_satiri(en_iyi)}")
if alt1 is not None:
    st.markdown(f"**Alternatif 1:** {arac_satiri(alt1)}")
if alt2 is not None:
    st.markdown(f"**Alternatif 2:** {arac_satiri(alt2)}")

en_onemli = ahp_sonuc.agirliklar.sort_values(ascending=False).head(2).index.tolist()
en_onemli_etiket = ", ".join(KRITER_ETIKETLERI.get(k, k) for k in en_onemli)
st.write(f"Bu arac, en onemli kriterlerde iyi sonuc verdigi icin onerildi: {en_onemli_etiket}.")

st.subheader("6) Disari Aktar")
st.download_button(
    "Siralama listesini CSV indir",
    data=sirali_df.to_csv(index=False).encode("utf-8"),
    file_name="topsis_siralama.csv",
    mime="text/csv",
    use_container_width=True,
)
