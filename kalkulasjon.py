from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from database import PANEL_DB
from geometry import poly_area, poly_perim, wall_lengths, beslag_beregning
from materialer import materialliste
from kappliste import lag_kappliste, kappliste_sammendrag


@dataclass(frozen=True)
class ProjectInput:
    navn:          str
    pnr:           str
    tnr:           str
    dato:          str
    maalestokk:    str
    rom_type:      str
    panel_key:     str
    pts:           list[tuple[float, float]]
    hoyde_m:       float
    panelbredde_m: float
    # dorer kan være (dk, ant) ELLER (dk, ant, wall_idx, offset_m)
    dorer:         list[tuple]
    beslag_valg:   list[str]


def beregn_prosjekt(
    inp: ProjectInput,
    pris_override: dict | None = None,
    breeam_multiplier: float = 1.0,
) -> dict[str, Any]:
    """Samler alle mengder, kalkulasjoner og nøkkeltall for prosjektet."""
    area  = poly_area(inp.pts)
    perim = poly_perim(inp.pts)
    wls   = wall_lengths(inp.pts)
    ov    = {
        "A": round(area, 2),
        "P": round(perim, 2),
        "V": round(area * inp.hoyde_m, 2),
        "H": inp.hoyde_m,
    }
    panel = PANEL_DB[inp.panel_key]

    # Normalize dorer til (dk, ant) for materialliste
    dorer_mat = [(d[0], d[1]) for d in inp.dorer]

    df_mat = materialliste(
        ov, inp.panel_key, inp.rom_type, dorer_mat,
        inp.beslag_valg, inp.panelbredde_m, wls, inp.pts,
        pris_override=pris_override,
        breeam_multiplier=breeam_multiplier,
    )
    df_kapp = lag_kappliste(
        inp.pts,
        round(inp.hoyde_m * 1000),
        round(inp.panelbredde_m * 1000),
        inp.rom_type,
    )
    sam    = kappliste_sammendrag(df_kapp)
    beslag = beslag_beregning(inp.pts, inp.hoyde_m)
    ant_veggpanel = sum(math.ceil(w / inp.panelbredde_m) for w in wls)

    return {
        "ov":           ov,
        "panel":        panel,
        "wls":          wls,
        "df_mat":       df_mat,
        "df_kapp":      df_kapp,
        "sam":          sam,
        "beslag":       beslag,
        "ant_veggpanel": ant_veggpanel,
        "tot_pris":     float(df_mat["Totalpris (kr)"].sum()) if not df_mat.empty else 0.0,
        "tot_co2":      float(df_mat["CO₂ (kg)"].sum())      if not df_mat.empty else 0.0,
    }


def kalkulasjon_sammendrag(result: dict[str, Any]) -> pd.DataFrame:
    ov = result["ov"]
    return pd.DataFrame([
        {"Nøkkeltall": "Gulvareal",  "Verdi": f"{ov['A']} m²"},
        {"Nøkkeltall": "Volum",      "Verdi": f"{ov['V']} m³"},
        {"Nøkkeltall": "Omkrets",    "Verdi": f"{ov['P']} m"},
        {"Nøkkeltall": "Kostnad",    "Verdi": f"{result['tot_pris']:,.0f} kr".replace(",", " ")},
        {"Nøkkeltall": "CO₂",       "Verdi": f"{result['tot_co2']:,.0f} kg".replace(",", " ")},
    ])
