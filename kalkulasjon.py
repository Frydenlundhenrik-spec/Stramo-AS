from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from database import PANEL_DB, DOR_DB
from construction import floor_depth, door_keys
from geometry import poly_area, poly_perim, wall_lengths, beslag_beregning, validate_wall_openings, validate_polygon
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
    apninger:      list[tuple] = None
    excluded_walls: tuple[int, ...] = ()


def beregn_prosjekt(
    inp: ProjectInput,
    pris_override: dict | None = None,
    breeam_multiplier: float = 1.0,
) -> dict[str, Any]:
    """Samler alle mengder, kalkulasjoner og nøkkeltall for prosjektet."""
    clear_height = inp.hoyde_m - floor_depth(inp.rom_type)
    validate_polygon(inp.pts)
    validate_wall_openings(inp.pts, clear_height, inp.dorer, inp.apninger or ())
    for door in inp.dorer:
        if door[1] <= 0:
            continue
        if inp.rom_type == "Fryserom" and door[0] not in door_keys(inp.rom_type, DOR_DB):
            raise ValueError("Velg fryseromsdør til fryserommet.")
        if DOR_DB[door[0]]["bh"] / 1000 > clear_height:
            raise ValueError("Døren er høyere enn fri høyde over ferdig gulv.")
    for opening in inp.apninger or []:
        if opening[4] < 0 or opening[3] <= 0 or opening[4] + opening[3] > clear_height:
            raise ValueError("Åpningen må ligge mellom ferdig gulv og underkant tak.")
    area  = poly_area(inp.pts)
    perim = poly_perim(inp.pts)
    wls   = wall_lengths(inp.pts)
    ov    = {
        "A": round(area, 2),
        "P": round(perim, 2),
        "V": round(area * clear_height, 2),
        "H": inp.hoyde_m,
    }
    panel = PANEL_DB[inp.panel_key]

    # Normalize dorer til (dk, ant) for materialliste
    dorer_mat = [(d[0], d[1]) for d in inp.dorer
                 if (d[2] if len(d)>2 else 0) not in inp.excluded_walls]

    df_kapp = lag_kappliste(
        inp.pts,
        round(inp.hoyde_m * 1000),
        round(inp.panelbredde_m * 1000),
        inp.rom_type,
        apninger=tuple(tuple(a) for a in (inp.apninger or [])),
        excluded_walls=tuple(inp.excluded_walls),
        floor_panel_mm=panel["t"],
    )
    df_mat = materialliste(
        ov, inp.panel_key, inp.rom_type, dorer_mat,
        inp.beslag_valg, inp.panelbredde_m, wls, inp.pts,
        pris_override=pris_override,
        breeam_multiplier=breeam_multiplier,
        excluded_walls=inp.excluded_walls,
        cut_list=df_kapp,
    )
    sam    = kappliste_sammendrag(df_kapp)
    beslag = beslag_beregning(inp.pts, inp.hoyde_m, inp.excluded_walls, panel["t"]/1000, clear_height, floor_angles=inp.rom_type=="Fryserom")
    ant_veggpanel = int(df_mat.loc[df_mat.Post.str.startswith("Vegg "), "Mengde"].sum())
    missing_prices = df_mat.loc[df_mat.Type.str.contains("PRIS MANGLER", regex=False), "Post"].tolist()

    return {
        "ov":           ov,
        "panel":        panel,
        "wls":          wls,
        "df_mat":       df_mat,
        "df_kapp":      df_kapp,
        "sam":          sam,
        "beslag":       beslag,
        "ant_veggpanel": ant_veggpanel,
        "missing_prices": missing_prices,
        "pricing_complete": not missing_prices,
        "tot_pris":     float(df_mat["Totalpris (kr)"].sum()) if not df_mat.empty else 0.0,
        "tot_co2":      float(df_mat["CO₂ (kg)"].sum())      if not df_mat.empty else 0.0,
    }


def kalkulasjon_sammendrag(result: dict[str, Any]) -> pd.DataFrame:
    ov = result["ov"]
    return pd.DataFrame([
        {"Nøkkeltall": "Gulvareal",  "Verdi": f"{ov['A']} m²"},
        {"Nøkkeltall": "Volum",      "Verdi": f"{ov['V']} m³"},
        {"Nøkkeltall": "Omkrets",    "Verdi": f"{ov['P']} m"},
        {"Nøkkeltall": "Kostnad" if result.get("pricing_complete", True) else "Delsum (priser mangler)",
         "Verdi": f"{result['tot_pris']:,.0f} kr".replace(",", " ")},
        {"Nøkkeltall": "CO₂",       "Verdi": f"{result['tot_co2']:,.0f} kg".replace(",", " ")},
    ])
