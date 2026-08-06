"""
Stramo-profil: logo og merkefarger.

Logoen ligger som PNG med gjennomsiktig bakgrunn i assets/. Den er konvertert
fra originalen «Stramo logo u tekst org.pdf». Skal logoen byttes ut, legg en ny
PNG på samme sti – alle tegninger og eksporter henter den herfra.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

LOGO_PATH  = Path(__file__).parent / "assets" / "stramo_logo.png"

# Farger hentet fra logoen
STRAMO_BLA  = "#0d3b54"
STRAMO_GUL  = "#e3e011"


def logo_finnes() -> bool:
    return LOGO_PATH.is_file()


@lru_cache(maxsize=1)
def logo_bilde():
    """Logoen som RGBA-array for matplotlib. None hvis filen mangler."""
    if not logo_finnes():
        return None
    try:
        import numpy as np
        from PIL import Image
        return np.asarray(Image.open(LOGO_PATH).convert("RGBA"))
    except Exception:
        return None


@lru_cache(maxsize=1)
def logo_sideforhold() -> float:
    """Bredde delt på høyde. Faller tilbake på logoens kjente format."""
    bilde = logo_bilde()
    if bilde is None:
        return 2.16
    return bilde.shape[1] / bilde.shape[0]


@lru_cache(maxsize=1)
def logo_data_uri() -> str | None:
    """Logoen som base64 data-URI, til bruk i HTML-eksporter. None hvis filen mangler."""
    if not logo_finnes():
        return None
    import base64
    b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"
