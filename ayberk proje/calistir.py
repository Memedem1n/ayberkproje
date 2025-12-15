"""
calistir.py

Amaç:
- Bu projeyi baska bir bilgisayarda "tek tusla" calistirmak.
- Varsa `.venv` sanal ortamini kullanmak, yoksa otomatik olusturmak.
- Gereken kutuphaneler eksikse ya da `requirements.txt` degistiyse kurulumu guncellemek.
- Sonunda Streamlit uygulamasini baslatmak.

Kullanim:
- Terminalden: `python calistir.py`
- IDE'de: `calistir.py` dosyasini acip Run tusuna basmak
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KurulumBilgisi:
    python_surumu: str
    gereklilikler_sha256: str


def proje_dizini() -> Path:
    """Proje kok dizinini (bu dosyanin oldugu klasor) dondurur."""

    return Path(__file__).resolve().parent


def venv_dizini(proje: Path) -> Path:
    """Sanal ortam dizini."""

    return proje / ".venv"


def venv_python_yolu(proje: Path) -> Path:
    """
    Sanal ortam python yolunu dondurur.
    - Windows: .venv/Scripts/python.exe
    - macOS/Linux: .venv/bin/python
    """

    if os.name == "nt":
        return venv_dizini(proje) / "Scripts" / "python.exe"
    return venv_dizini(proje) / "bin" / "python"


def komut_calistir(komut: list[str], *, proje: Path) -> None:
    """Komutlari proje klasorunden calistirir ve hata olursa durdurur."""

    print("\n> " + " ".join(komut))
    subprocess.run(komut, cwd=str(proje), check=True)


def sha256_hesapla(dosya: Path) -> str:
    """Bir dosyanin SHA256 ozetini hesaplar."""

    h = hashlib.sha256()
    with dosya.open("rb") as f:
        for parca in iter(lambda: f.read(1024 * 1024), b""):
            h.update(parca)
    return h.hexdigest()


def kurulum_bilgisi_yolu(proje: Path) -> Path:
    """Kurulum bilgisi dosyasi (requirements degisimi icin)."""

    return venv_dizini(proje) / "kurulum_bilgisi.json"


def kurulum_bilgisi_oku(dosya: Path) -> KurulumBilgisi | None:
    """Kurulum bilgisi dosyasini okur; yoksa None dondurur."""

    if not dosya.exists():
        return None
    try:
        veri = json.loads(dosya.read_text(encoding="utf-8"))
        python_surumu = str(veri.get("python_surumu", "")).strip()
        gereklilikler_sha256 = str(veri.get("gereklilikler_sha256", "")).strip()
        if not python_surumu or not gereklilikler_sha256:
            return None
        return KurulumBilgisi(python_surumu=python_surumu, gereklilikler_sha256=gereklilikler_sha256)
    except Exception:
        return None


def kurulum_bilgisi_yaz(dosya: Path, bilgi: KurulumBilgisi) -> None:
    """Kurulum bilgisi dosyasini yazar."""

    dosya.write_text(
        json.dumps(
            {"python_surumu": bilgi.python_surumu, "gereklilikler_sha256": bilgi.gereklilikler_sha256},
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def modul_kontrolu(venv_python: Path, *, proje: Path) -> bool:
    """
    Ortam saglik kontrolu:
    - Gerekli moduller import edilebiliyor mu?
    """

    kontrol_kodu = "import streamlit, pandas, numpy, openpyxl; print('tamam')"
    sonuc = subprocess.run([str(venv_python), "-c", kontrol_kodu], cwd=str(proje))
    return sonuc.returncode == 0


def venv_olustur(proje: Path) -> None:
    """
    Sanal ortam olusturur.

    Not:
    - Bu islem, bu dosyayi calistiran Python surumunu kullanir.
    """

    print("Sanal ortam olusturuluyor (.venv)...")
    komut_calistir([sys.executable, "-m", "venv", str(venv_dizini(proje))], proje=proje)


def venv_python_calisiyor_mu(venv_python: Path, *, proje: Path) -> bool:
    """
    Sanal ortam Python'u calisiyor mu?

    Not:
    - `.venv` baska bir bilgisayardan kopyalanirsa, Python ikili dosyalari/DLL bagimliliklari
      nedeniyle calismayabilir. Bu durumda venv'i yeniden olusturmak gerekir.
    """

    try:
        sonuc = subprocess.run([str(venv_python), "-V"], cwd=str(proje))
        return sonuc.returncode == 0
    except Exception:
        return False



def gereklilikleri_kur_veya_guncelle(proje: Path, venv_python: Path, *, guncelle: bool) -> None:
    """
    requirements.txt'e gore kutuphaneleri kurar.
    - guncelle=True ise paketleri gerekirse yukselterek kurar.
    """

    print("Gereklilikler kuruluyor/guncelleniyor...")
    komut_calistir(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        proje=proje,
    )

    pip_komutu = [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"]
    if guncelle:
        pip_komutu.insert(4, "--upgrade")
    komut_calistir(pip_komutu, proje=proje)


def streamlit_baslat(proje: Path, venv_python: Path) -> int:
    """Streamlit uygulamasini baslatir."""

    print("\nUygulama baslatiliyor...")
    sonuc = subprocess.run(
        [
            str(venv_python),
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=str(proje),
    )
    return int(sonuc.returncode)


def main() -> int:
    proje = proje_dizini()
    os.chdir(proje)

    # Basit dosya kontrolu (kopyalama hatalarini erken yakalamak icin).
    gerekli_dosyalar = ["app.py", "utils.py", "requirements.txt", "dataset.xlsx"]
    eksikler = [d for d in gerekli_dosyalar if not (proje / d).exists()]
    if eksikler:
        print("Hata: Projede eksik dosya(lar) var: " + ", ".join(eksikler))
        return 1

    venv_python = venv_python_yolu(proje)
    if venv_python.exists() and not venv_python_calisiyor_mu(venv_python, proje=proje):
        print("Uyari: Sanal ortam bozuk veya baska bilgisayardan kopyalanmis olabilir. Yeniden olusturuluyor...")
        shutil.rmtree(venv_dizini(proje), ignore_errors=True)

    if not venv_python.exists():
        venv_olustur(proje)
        if not venv_python.exists():
            print("Hata: Sanal ortam python yolu bulunamadi: " + str(venv_python))
            return 1

    gereklilikler_sha = sha256_hesapla(proje / "requirements.txt")
    bilgi_dosyasi = kurulum_bilgisi_yolu(proje)
    eski_bilgi = kurulum_bilgisi_oku(bilgi_dosyasi)

    # "Gerekirse guncelle" mantigi:
    # - requirements.txt degismisse veya moduller import edilemiyorsa kurulum/guncelleme yap.
    kurulum_gerekli = (eski_bilgi is None) or (eski_bilgi.gereklilikler_sha256 != gereklilikler_sha)
    if not kurulum_gerekli and not modul_kontrolu(venv_python, proje=proje):
        kurulum_gerekli = True

    if kurulum_gerekli:
        gereklilikleri_kur_veya_guncelle(proje, venv_python, guncelle=True)
        python_surumu = subprocess.check_output(
            [str(venv_python), "-c", "import sys; print(sys.version.split()[0])"],
            cwd=str(proje),
            text=True,
        ).strip()
        kurulum_bilgisi_yaz(
            bilgi_dosyasi,
            KurulumBilgisi(python_surumu=python_surumu, gereklilikler_sha256=gereklilikler_sha),
        )

    return streamlit_baslat(proje, venv_python)


if __name__ == "__main__":
    raise SystemExit(main())
