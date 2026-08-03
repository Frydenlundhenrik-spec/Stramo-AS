from __future__ import annotations
import math
from typing import Sequence
import pandas as pd
import streamlit as st
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
    wls_m = wall_lengths(pts)
    rader: list[dict] = []
    el_nr = 1
    rest_mm = 0

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
                sill_mm = ap_sill * 1000
                top_mm  = sill_mm + ap_h * 1000
                cuts.append((sill_mm, top_mm))
        return cuts

    for vi, wl_m in enumerate(wls_m):
        vegg_label = f"Vegg {vi+1}"
        L_mm = round(wl_m * 1000)
        brukt_mm = 0

        def _legg_til(base_type, bredde, x_start):
            nonlocal el_nr
            cuts = _cuts_for_panel(vi, x_start, bredde)
            deler = _panel_utsparing_deler(base_type, bredde, H_mm, cuts)
            pnavn = f"V{el_nr}"
            for typ, b, h, merk in deler:
                rader.append(dict(Elementnavn=pnavn, Vegg=vegg_label, Type=typ,
                                  Bredde_mm=b, Høyde_mm=h,
                                  Areal_m2=round(b/1000*h/1000, 3), Merknad=merk))
            el_nr += 1

        if rest_mm > 0:
            bredde = min(rest_mm, L_mm)
            _legg_til("Rest fra forrige", bredde, brukt_mm)
            brukt_mm += bredde
            rest_mm = max(rest_mm - L_mm, 0)

        while brukt_mm + pw_mm <= L_mm:
            _legg_til("Hel", pw_mm, brukt_mm)
            brukt_mm += pw_mm

        remaining = L_mm - brukt_mm
        if remaining > 0:
            cuts = _cuts_for_panel(vi, brukt_mm, remaining)
            deler = _panel_utsparing_deler("Kapp (videreføres)", remaining, H_mm, cuts)
            pnavn = f"V{el_nr}"
            for typ, b, h, merk in deler:
                if typ == "Kapp (videreføres)":
                    merk = f"Kapp {remaining} mm – rest {pw_mm-remaining} mm videreføres"
                rader.append(dict(Elementnavn=pnavn, Vegg=vegg_label, Type=typ,
                                  Bredde_mm=b, Høyde_mm=h,
                                  Areal_m2=round(b/1000*h/1000, 3), Merknad=merk))
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
