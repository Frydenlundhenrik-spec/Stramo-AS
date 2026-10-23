from __future__ import annotations
from construction import roof_outline
import math
from typing import Sequence
import pandas as pd
import streamlit as st
from construction import floor_depth, floor_outline, wall_panel_layout
from geometry import poly_area, wall_lengths, Point
from panel_engine import generate_roof_floor_panels


def _panel_utsparing_deler(base_type, bredde_mm, H_mm, ap_cuts):
    """
    Splitter ett panel i deler basert på utsparinger.
    ap_cuts: liste med (sill_mm, top_mm).
    Returnerer liste med (type, bredde_mm, høyde_mm, merknad).
    """
    if not ap_cuts:
        return [(base_type, int(bredde_mm), int(H_mm), "")]

    breaks = sorted(set([0, H_mm] + [v for sill, top in ap_cuts
                                      for v in ([int(sill)] if sill > 0 else []) + [int(top)]]))
    deler = []
    for i in range(len(breaks) - 1):
        y0, y1 = breaks[i], breaks[i+1]
        h = y1 - y0
        if h < 1:
            continue
        mid = (y0 + y1) / 2
        er_utsparing = any(sill <= mid <= top for sill, top in ap_cuts)
        if er_utsparing:
            deler.append(("Utsparing", int(bredde_mm), int(h),
                          f"Utsparing {round(y0)}–{round(y1)} mm (ikke bestilles)"))
        else:
            merknad = f"Del av panel med utsparing · {round(y0)}–{round(y1)} mm" if len(breaks) > 2 else ""
            deler.append((base_type, int(bredde_mm), int(h), merknad))
    return deler


@st.cache_data(show_spinner=False)
def lag_kappliste(
    pts: Sequence[Point],
    H_mm: int,
    pw_mm: int,
    rom_type: str,
    tak_kapp_plassering: str = "slutt",
    apninger: tuple = (),
    excluded_walls: tuple = (),
    floor_panel_mm: int = 100,
) -> pd.DataFrame:
    """
    Kappliste for vegg, tak og gulv.

    Vegger:
      - Kontinuerlig V-nummerering.
      - Kapp-rest fra forrige vegg brukes først på neste vegg.
      - Paneler med utsparinger splittes i sub-rader (over/under åpning).

    Tak/gulv:
      - Elementene har samme bredde som veggelementene.
      - De går fra én vegg til motsatt vegg.
      - De klippes mot polygonet, slik at skrå/avskåret hjørne får riktig geometri.
      - Kapp kan ligge først eller sist. Standard er sluttkapp.
    """
    rader: list[dict] = []

    def _cuts_for_panel(wall_idx, x_start_mm, panel_w_mm):
        """Finn utsparinger som overlapper dette panelet, returner (sill_mm, top_mm)."""
        cuts = []
        x_end_mm = x_start_mm + panel_w_mm
        for ap in apninger:
            ap_wall, ap_off, ap_w, ap_h, ap_sill, *_ = ap
            if int(ap_wall) != wall_idx:
                continue
            off_mm = ap_off * 1000; w_mm = ap_w * 1000
            if off_mm < x_end_mm and off_mm + w_mm > x_start_mm:
                sill_mm = (floor_depth(rom_type) + ap_sill) * 1000
                top_mm  = sill_mm + ap_h * 1000
                cuts.append((sill_mm, top_mm))
        return cuts

    for panel in wall_panel_layout(pts,pw_mm,floor_panel_mm/1000,excluded_walls):
        cuts = _cuts_for_panel(panel['wall'],panel['start_mm'],panel['width_mm'])
        for typ,b,h,merk in _panel_utsparing_deler(panel['kind'],panel['width_mm'],H_mm,cuts):
            rader.append(dict(Elementnavn=panel['name'], Vegg=f"Vegg {panel['wall']+1}", Type=typ,
                              Bredde_mm=b, Høyde_mm=h, Areal_m2=round(b*h/1e6,3), Merknad=merk))

    # Takpaneler – polygonbasert løsning.
    cut_pos = "start" if str(tak_kapp_plassering).lower().startswith("start") else "end"
    takpaneler = generate_roof_floor_panels(roof_outline(pts,floor_panel_mm/1000,rom_type), pw_mm, prefix="T", label="Tak", cut_position=cut_pos)
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
        gulvpaneler = generate_roof_floor_panels(floor_outline(pts,floor_panel_mm/1000), pw_mm, prefix="G", label="Gulv PIR", cut_position=cut_pos)
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

        # Floor fibreboard is listed as net area; sheet cutting is listed separately.
        area_m2 = poly_area(pts)
        rader.append(dict(
            Elementnavn="SP1", Vegg="Gulv", Type="Gulvfiberplate 12 mm",
            Bredde_mm="", Høyde_mm="", Areal_m2=round(area_m2, 3),
            Merknad=f"12 mm gulvfiberplate innenfor vegger, se egen kappliste · {area_m2:.2f} m²"
        ))

    return pd.DataFrame(rader)


def kappliste_sammendrag(df_kapp: pd.DataFrame) -> dict:
    VEGG_TYPER = ["Hel", "Kapp (videreføres)", "Rest fra forrige"]
    TAK_TYPER = ["Tak – hel", "Tak – startkapp", "Tak – sluttkapp"]
    GULV_TYPER = ["Gulv PIR – hel", "Gulv PIR – startkapp", "Gulv PIR – sluttkapp"]

    vegg_df = df_kapp[df_kapp["Vegg"].str.startswith("Vegg ")]
    tak_df = df_kapp[df_kapp["Type"].isin(TAK_TYPER)]
    gulv_df = df_kapp[df_kapp["Type"].isin(GULV_TYPER)]
    spon_df = df_kapp[df_kapp["Type"].isin(("Gulvfiberplate 12 mm", "Beskyttelsesfiner 12 mm"))]

    return dict(
        hele=df_kapp.loc[df_kapp["Type"] == "Hel", "Elementnavn"].nunique(),
        kapp=df_kapp.loc[df_kapp["Type"] == "Kapp (videreføres)", "Elementnavn"].nunique(),
        rest=df_kapp.loc[df_kapp["Type"] == "Rest fra forrige", "Elementnavn"].nunique(),
        tot_panel=vegg_df.Elementnavn.nunique(),
        tak=len(tak_df),
        gulv=len(gulv_df),
        spon=len(spon_df),
    )


def panel_order_rows(cut: pd.DataFrame, wall_height_mm: int, panel_width_mm: int):
    """One full-width blank per named panel, shared by prices and purchase lists.

    Opening sub-pieces keep the same name and therefore never buy another blank.
    Net cutting dimensions are kept separately from the ordered blank area.
    """
    panels = cut[pd.to_numeric(cut.Bredde_mm, errors="coerce").notna()]
    rows = []
    for (zone, name), parts in panels.groupby(["Vegg", "Elementnavn"], sort=False):
        length = wall_height_mm if str(zone).startswith("Vegg") else int(parts.Høyde_mm.sum())
        rows.append(dict(Vegg=zone, Elementnavn=name, Leveringslengde_mm=length,
                         Bredde_mm=panel_width_mm, Deler_stk=len(parts),
                         Løpemeter=float(parts.Høyde_mm.sum()) / 1000,
                         Areal_m2=float(parts.Areal_m2.sum()),
                         Bestill_m2=panel_width_mm * length / 1_000_000))
    return pd.DataFrame(rows)
