from __future__ import annotations
import math
from typing import Sequence
import pandas as pd
import streamlit as st
from geometry import poly_area, wall_lengths, Point
from panel_engine import generate_roof_floor_panels


@st.cache_data(show_spinner=False)
def lag_kappliste(
    pts: Sequence[Point],
    H_mm: int,
    pw_mm: int,
    rom_type: str,
    tak_kapp_plassering: str = "slutt",
) -> pd.DataFrame:
    """
    Kappliste for vegg, tak og gulv.

    Vegger:
      - Kontinuerlig V-nummerering.
      - Kapp-rest fra forrige vegg brukes først på neste vegg.

    Tak/gulv:
      - Elementene har samme bredde som veggelementene.
      - De går fra én vegg til motsatt vegg.
      - De klippes mot polygonet, slik at skrå/avskåret hjørne får riktig geometri.
      - Kapp kan ligge først eller sist. Standard er sluttkapp.
    """
    wls_m = wall_lengths(pts)
    rader: list[dict] = []
    el_nr = 1
    rest_mm = 0

    for vi, wl_m in enumerate(wls_m):
        vegg_label = f"Vegg {vi+1}"
        L_mm = round(wl_m * 1000)
        brukt_mm = 0

        if rest_mm > 0:
            bredde = min(rest_mm, L_mm)
            rader.append(dict(
                Elementnavn=f"V{el_nr}", Vegg=vegg_label, Type="Rest fra forrige",
                Bredde_mm=int(bredde), Høyde_mm=int(H_mm),
                Areal_m2=round(bredde/1000 * H_mm/1000, 3),
                Merknad=f"Kapp-rest {rest_mm} mm fra forrige element"
            ))
            brukt_mm += bredde
            el_nr += 1
            rest_mm = max(rest_mm - L_mm, 0)

        while brukt_mm + pw_mm <= L_mm:
            rader.append(dict(
                Elementnavn=f"V{el_nr}", Vegg=vegg_label, Type="Hel",
                Bredde_mm=int(pw_mm), Høyde_mm=int(H_mm),
                Areal_m2=round(pw_mm/1000 * H_mm/1000, 3), Merknad=""
            ))
            brukt_mm += pw_mm
            el_nr += 1

        remaining = L_mm - brukt_mm
        if remaining > 0:
            rader.append(dict(
                Elementnavn=f"V{el_nr}", Vegg=vegg_label, Type="Kapp (videreføres)",
                Bredde_mm=int(remaining), Høyde_mm=int(H_mm),
                Areal_m2=round(remaining/1000 * H_mm/1000, 3),
                Merknad=f"Kapp {remaining} mm – rest {pw_mm-remaining} mm videreføres"
            ))
            el_nr += 1
            rest_mm = pw_mm - remaining

    # Takpaneler – polygonbasert løsning.
    cut_pos = "start" if str(tak_kapp_plassering).lower().startswith("start") else "end"
    takpaneler = generate_roof_floor_panels(pts, pw_mm, prefix="T", label="Tak", cut_position=cut_pos)
    for p in takpaneler:
        rader.append(dict(
            Elementnavn=p.name,
            Vegg="Tak",
            Type=p.kind,
            Bredde_mm=p.width_mm,
            Høyde_mm=p.span_mm,
            Areal_m2=p.area_m2,
            Merknad=p.note,
        ))

    # Gulvpaneler – kun fryserom, samme polygonlogikk som tak.
    if "Fryserom" in rom_type:
        gulvpaneler = generate_roof_floor_panels(pts, pw_mm, prefix="G", label="Gulv PIR", cut_position=cut_pos)
        for p in gulvpaneler:
            rader.append(dict(
                Elementnavn=p.name,
                Vegg="Gulv",
                Type=p.kind,
                Bredde_mm=p.width_mm,
                Høyde_mm=p.span_mm,
                Areal_m2=p.area_m2,
                Merknad=p.note,
            ))

        # Sponplate oppgis som totalareal, men beholdes som én post.
        area_m2 = poly_area(pts)
        rader.append(dict(
            Elementnavn="SP1", Vegg="Gulv", Type="Sponplate m/ plastbelegg",
            Bredde_mm="", Høyde_mm="", Areal_m2=round(area_m2, 3),
            Merknad=f"Sponplate med plastbelegg over gulvpanel · {area_m2:.2f} m²"
        ))

    return pd.DataFrame(rader)


def kappliste_sammendrag(df_kapp: pd.DataFrame) -> dict:
    VEGG_TYPER = ["Hel", "Kapp (videreføres)", "Rest fra forrige"]
    TAK_TYPER = ["Tak – hel", "Tak – startkapp", "Tak – sluttkapp"]
    GULV_TYPER = ["Gulv PIR – hel", "Gulv PIR – startkapp", "Gulv PIR – sluttkapp"]

    vegg_df = df_kapp[df_kapp["Type"].isin(VEGG_TYPER)]
    tak_df = df_kapp[df_kapp["Type"].isin(TAK_TYPER)]
    gulv_df = df_kapp[df_kapp["Type"].isin(GULV_TYPER)]
    spon_df = df_kapp[df_kapp["Type"] == "Sponplate m/ plastbelegg"]

    return dict(
        hele=len(df_kapp[df_kapp["Type"] == "Hel"]),
        kapp=len(df_kapp[df_kapp["Type"] == "Kapp (videreføres)"]),
        rest=len(df_kapp[df_kapp["Type"] == "Rest fra forrige"]),
        tot_panel=len(vegg_df),
        tak=len(tak_df),
        gulv=len(gulv_df),
        spon=len(spon_df),
    )
