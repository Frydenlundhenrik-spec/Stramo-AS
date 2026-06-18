from __future__ import annotations
import math
import pandas as pd
from database import PANEL_DB, GULV_DB_KJOL, GULV_DB_FRYS, BESLAG_DB, DOR_DB
from geometry import beslag_beregning, poly_perim

# ── NS 3420 / kode-mapping ────────────────────────────────────────────────────
_NS: dict[str, str] = {
    "vegg":    "NS3420-H / Panel vegg",
    "tak":     "NS3420-H / Panel tak",
    "gulv_pir":"NS3420-H / PIR gulv",
    "gulv_bet":"NS3420-54 / Gulv avrettet",
    "gulv_spon":"NS3420-54 / Sponplate",
    "dor":     "NS3420-H40 / Dør kjøl",
    "beslag":  "NS3420-H / Dørbeslag",
    "ukan":    "NS3420-H / U-kanal",
    "beslag_h":"NS3420-H / Hjørnebeslag",
}


def materialliste(
    ov: dict,
    panel_key: str,
    rom_type: str,
    dorer: list[tuple[str, int]],
    beslag_valg: list[str],
    pw_m: float,
    wls: list[float],
    pts_polygon: list[tuple[float, float]],
    pris_override: dict | None = None,
    breeam_multiplier: float = 1.0,
) -> pd.DataFrame:
    """
    Bygger fullstendig materialliste.
    pris_override: dict med {post_key: ny_enhetspris} – for prisjustering i UI.
    breeam_multiplier: prisjustering for miljøkrav (1.0 = ingen).
    """
    pan = PANEL_DB[panel_key]
    H   = ov["H"]
    override = pris_override or {}
    rows = []

    def ep(key: str, default: float) -> float:
        return override.get(key, default) * breeam_multiplier

    # ── Vegger ──────────────────────────────────────────────────────────────
    for i, wl in enumerate(wls):
        np_ = math.ceil(wl / pw_m)
        unit_p = ep(f"vegg_{i}", pan["pris"] * pw_m * H)
        rows.append(dict(
            Post=f"Vegg {i+1}", Type=pan["label"], Enhet="stk",
            Mengde=np_, **_kr(unit_p, np_), NS3420=_NS["vegg"],
            CO2_k=pan["co2"] * pw_m * H,
        ))

    # ── Tak ─────────────────────────────────────────────────────────────────
    unit_tak = ep("tak", pan["pris"])
    rows.append(dict(
        Post="Tak (panel)", Type=pan["label"], Enhet="m²",
        Mengde=ov["A"], **_kr(unit_tak, ov["A"]), NS3420=_NS["tak"],
        CO2_k=pan["co2"],
    ))

    # ── Gulv ─────────────────────────────────────────────────────────────────
    if rom_type.startswith("Kjølerom"):
        pass  # Kjølerom: gulvet er eksisterende betong, ikke kalkulert
    else:
        unit_pir = ep("gulv_pir", 650)
        rows.append(dict(
            Post="Gulv – PIR panel 100 mm", Type="PIR 100 mm gulvpanel",
            Enhet="m²", Mengde=ov["A"], **_kr(unit_pir, ov["A"]),
            NS3420=_NS["gulv_pir"], CO2_k=10.2,
        ))
        unit_spon = ep("gulv_spon", 330)
        rows.append(dict(
            Post="Gulv – sponplate m/ plastbelegg", Type="Sponplate plastbelegg",
            Enhet="m²", Mengde=ov["A"], **_kr(unit_spon, ov["A"]),
            NS3420=_NS["gulv_spon"], CO2_k=8.5,
        ))

    # ── Dører ─────────────────────────────────────────────────────────────────
    nd = 0
    for dk, ant in dorer:
        if ant > 0:
            d = DOR_DB[dk]
            unit_dor = ep(f"dor_{dk}", d["pris"])
            rows.append(dict(
                Post="Dør", Type=d["label"], Enhet="stk",
                Mengde=ant, **_kr(unit_dor, ant),
                NS3420=_NS["dor"], CO2_k=0.0,
            ))
            nd += ant

    # ── Dørbeslag ─────────────────────────────────────────────────────────────
    for bk in beslag_valg:
        b = BESLAG_DB[bk]
        ant = b["ape"] * max(nd, 1)
        unit_b = ep(f"beslag_{bk}", b["pris"])
        rows.append(dict(
            Post="Dørbeslag", Type=b["label"], Enhet="stk",
            Mengde=ant, **_kr(unit_b, ant),
            NS3420=_NS["beslag"], CO2_k=0.0,
        ))

    # ── U-kanal ───────────────────────────────────────────────────────────────
    UKAN_M  = 3.0
    unit_uk = ep("ukan", 220)
    lm_brutto = round(poly_perim(pts_polygon) * 1.05, 2)
    stk_uk = math.ceil(lm_brutto / UKAN_M)
    rows.append(dict(
        Post="U-kanal 80 mm (gulv→vegg)",
        Type="U-kanal 80 mm, rustfritt stål (3 m stenger)",
        Enhet="stk", Mengde=stk_uk, **_kr(unit_uk, stk_uk),
        NS3420=_NS["ukan"], CO2_k=3.0 * 0.6,
    ))

    # ── Hjørnebeslag ──────────────────────────────────────────────────────────
    bb = beslag_beregning(pts_polygon, H)
    unit_inn = ep("beslag_inn", 185)
    unit_ut  = ep("beslag_ut",  265)
    rows.append(dict(
        Post="Innv. hjørnebeslag 50×50 mm",
        Type="L-profil 50×50 mm, 90°, rustfritt (2,5 m)",
        Enhet="stk", Mengde=bb["stk_inn"], **_kr(unit_inn, bb["stk_inn"]),
        NS3420=_NS["beslag_h"], CO2_k=2.5 * 0.8,
    ))
    rows.append(dict(
        Post="Utv. hjørnebeslag 50×125 mm",
        Type="L-profil 50×125 mm, 90°, rustfritt (2,5 m)",
        Enhet="stk", Mengde=bb["stk_ut"], **_kr(unit_ut, bb["stk_ut"]),
        NS3420=_NS["beslag_h"], CO2_k=2.5 * 0.8,
    ))

    df = pd.DataFrame(rows)
    df["CO₂ (kg)"] = (df["Mengde"] * df["CO2_k"]).round(1)
    df = df.drop(columns=["CO2_k"])
    df = df.rename(columns={"EP": "Enhetspris (kr)", "TP": "Totalpris (kr)"})
    df["Mengde"] = df["Mengde"].round(2)
    return df


def _kr(ep: float, mengde: float) -> dict:
    return {"EP": round(ep), "TP": round(ep * mengde)}
