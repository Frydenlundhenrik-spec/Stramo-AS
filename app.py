from __future__ import annotations

import math
import io
import base64
from datetime import datetime
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from construction import door_keys, floor_depth
from database import BESLAG_DB, DOR_DB, FORM_MALER, PANELER, load_databases
from geometry import wall_lengths, validate_polygon, l_polygon, door_dimensions, transform_polygon
from kalkulasjon import ProjectInput, beregn_prosjekt, kalkulasjon_sammendrag
from fdv import lag_fdv_oversikt, lag_fdv_tekst
from build_standard_fdv import lag_standard_fdv_pdf
from montasje import (
    tegn_plantegning, tegn_snitt, tegn_3d_modell,
    tegn_taktegning, tegn_veggoppstaltt, tegn_produksjonsfigurer,
    figur_som_png, figur_som_pdf, figurer_som_samlet_pdf, lag_tegningsinfo,
)
from ifc_export import gen_ifc
from kappliste import panel_order_rows
from export_excel import lag_excel
from export_pdf import lag_enkel_pdf, lag_tilbuds_pdf
from project_ui import (prepare_project, upload_project, capture_room, room_controls, project_download, assembly_ui, new_room_controls, finishing_ui)
from branding import LOGO_PATH, logo_finnes, logo_data_uri
from thermal_ui import thermal_inputs, thermal_ui

st.set_page_config(
    page_title="Stramo kjøleromssystem",
    page_icon=str(LOGO_PATH) if logo_finnes() else "❄️",
    layout="wide",
)

prepare_project()

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  html,body,[class*="css"]{font-family:'Inter',sans-serif;}
  .block-container{padding:1.2rem 2rem 2rem 2rem;}
  h1,h2,h3{color:#1a3a5c;}
  section[data-testid="stSidebar"]{background:#dce8f5;}
  .stButton>button,.stDownloadButton>button{
    border-radius:8px;border:none;background:#1a3a5c;
    color:#fff;font-weight:600;padding:.45rem 1rem;}
  .stButton>button:hover,.stDownloadButton>button:hover{background:#0d2540;}
  .card{background:#fff;padding:14px 18px;border-radius:12px;
    border:1px solid #d1e3f5;box-shadow:0 2px 6px rgba(0,0,0,.05);margin-bottom:.7rem;}
  .ct{font-size:12px;font-weight:600;color:#6b7280;margin-bottom:3px;}
  .cv{font-size:22px;font-weight:700;color:#1a3a5c;}
  .cs{font-size:11px;color:#9ca3af;}
</style>
""", unsafe_allow_html=True)

load_databases()

# ── BREEAM-konfigurasjon (tilpasset kjølerom) ──────────────────────────────────
BREEAM_MULTIPLIERS = {
    "Ingen":       1.00,
    "Pass":        1.02,
    "Good":        1.04,
    "Very Good":   1.07,
    "Excellent":   1.10,
    "Outstanding": 1.14,
}


def update_l_side(changed, previous):
    group = list(range(changed % 2, 6, 2))
    total = max(group, key=lambda i: previous[i])
    parts = [i for i in group if i != total]
    anchor_key = f"ed_l_anchor_{changed % 2}"
    anchor = st.session_state.get(anchor_key, parts[0]) if changed == total else changed
    if anchor not in parts:
        anchor = parts[0]
    other = next(i for i in parts if i != anchor)
    remainder = st.session_state[f"l_side_{total}"] - st.session_state[f"l_side_{anchor}"]
    if remainder < 100:
        st.session_state[f"l_side_{changed}"] = previous[changed]
        st.session_state["ed_l_error"] = "Endringen ble ikke brukt: begge delmål må være minst 100 mm og mindre enn totalmålet."
        return
    st.session_state[f"l_side_{other}"] = remainder
    st.session_state[anchor_key] = anchor
    st.session_state.pop("ed_l_error", None)


def card(t: str, v: str, s: str = "") -> None:
    sub = f'<div class="cs">{s}</div>' if s else ""
    st.markdown(
        f'<div class="card"><div class="ct">{t}</div>'
        f'<div class="cv">{v}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _beregn_cached(
    panel_key: str, rom_type: str, pts_tuple: tuple,
    H: float, pw_m: float, dorer_tuple: tuple,
    beslag_tuple: tuple, navn: str, pnr: str,
    tnr: str, dato: str, maalestokk: str,
    pris_json: str, breeam_mult: float,
    apninger_tuple: tuple = (),
) -> dict[str, Any]:
    import json
    pris_override = json.loads(pris_json) if pris_json else {}
    dorer_mat = list(dorer_tuple)
    inp = ProjectInput(
        navn, pnr, tnr, dato, maalestokk, rom_type, panel_key,
        list(pts_tuple), H, pw_m, dorer_mat, list(beslag_tuple),
        apninger=list(apninger_tuple),
    )
    return beregn_prosjekt(inp, pris_override=pris_override, breeam_multiplier=breeam_mult)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    upload_project()
    new_room_controls()
    if logo_finnes():
        st.image(str(LOGO_PATH), width=170)
    else:
        st.title("❄️ Stramo")
    st.caption("Kalkulasjon · FDV · Montasje · Elementer")

    # Keep an open session on the calculation page after removing the old menu item.
    if st.session_state.get("ed_module") == "U-verdi og varmetap":
        st.session_state["ed_module"] = "Kalkulasjon"
    modul = st.radio(
        "Velg modul",
        ["Kalkulasjon", "FDV", "Montasjetegninger", "Elementer", "Rom og sammenstilling", "Transport"],
        key="ed_module",
    )

    # ── Prosjektinfo ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📋 Prosjektinfo")
    navn        = st.text_input("Romnavn / prosjektnavn", st.session_state.get("navn", ""), key="ed_name",
                                 placeholder="Skriv inn prosjektnavn...")
    pnr         = st.text_input("Prosjektnr", st.session_state.get("pnr", "1001"), key="ed_pnr")
    tnr         = st.text_input("Tegningsnr", st.session_state.get("tnr", "A101"), key="ed_tnr")
    dato        = st.text_input("Dato", st.session_state.get("dato", datetime.today().strftime("%d.%m.%Y")), key="ed_date")
    maalestokk  = st.text_input("Målestokk", st.session_state.get("maalestokk", "1:10"), key="ed_scale")

    st.caption("Lagre arbeidet med «Last ned prosjektfil» nederst i sidepanelet.")

    # ── Romtype og panel ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("🌡️ Romtype og panel")
    rom_type = st.radio("Romtype", ["Kjølerom", "Fryserom"], key="ed_room_type")

    if rom_type == "Fryserom":
        st.caption("22 mm lekter → gulvpanel som vegg/tak → vegger på gulvpanel → 12 mm gulvplate innenfor vegger.")
        st.number_input("Gulvplate bredde (mm)",min_value=100,max_value=10000,value=1500,key="ed_finer_width")
        st.number_input("Gulvplate lengde (mm)",min_value=100,max_value=10000,value=3000,key="ed_finer_length")
    with st.expander("Tilbehør – mengder for dette rommet"):
        st.caption("Oppgi antall patroner, bokser og alarmer, og meter pakning. 0 betyr ikke angitt; ingen mengde anslås automatisk.")
        for accessory, label in (("fugemasse", "Fugemasse (stk)"), ("skum", "Skum (stk)"),
                                 ("pakninger", "Pakninger (m)"), ("alarm", "Alarm (stk)")):
            if accessory == "pakninger":
                st.number_input(label, min_value=0.0, max_value=1000000.0, value=0.0, step=0.1, key=f"ed_accessory_{accessory}")
            else:
                st.number_input(label, min_value=0, max_value=1000000, value=0, key=f"ed_accessory_{accessory}")
    st.subheader("Kapp og bestillingsgrunnlag")
    st.caption("Beslag: 10 % svinn/kapp, avrundet opp til hele 2500 mm lengder. Ingen prosentvis kapptillegg på paneler eller gulvplater.")
    # Alle paneltyper kan velges fritt
    _panel_keys = list(PANELER.keys())
    _documented_panels = {"PIR 80 mm", "PIR 100 mm", "PIR 120 mm"}
    _panel_labels = {k: f"{PANELER[k].navn}  (U={PANELER[k].u_verdi} W/m²K"
                     + (")" if k in _documented_panels else " – ikke dokumentert)") for k in _panel_keys}
    default_panel = "PIR 80 mm" if rom_type == "Kjølerom" else "PIR 100 mm"
    default_idx   = _panel_keys.index(default_panel)
    panel_key = st.selectbox(
        "Paneltype",
        _panel_keys,
        index=default_idx,
        format_func=lambda k: _panel_labels[k],
        key="ed_panel",
    )
    pan_info = PANELER[panel_key]
    from purchase_summary import estimated_panel_weight, BALEX_WEIGHTS
    st.caption(f"Automatisk panelvekt: {estimated_panel_weight(panel_key):g} kg/m² · " + ("Balex produktdatablad" if panel_key in BALEX_WEIGHTS else "ESTIMAT"))
    st.info(
        f"U-verdi: {pan_info.u_verdi} W/m²K  ·  "
        f"CO₂: {pan_info.co2_kg_m2} kg/m²  ·  "
        f"Pris: {pan_info.pris_nok_m2} kr/m²"
    )
    if panel_key not in _documented_panels:
        st.caption("U-verdien over er en eldre katalogverdi uten tilhørende produktdokumentasjon. Oppgi dokumentert U-verdi i varmeberegningen før den brukes der.")
    thermal_data = thermal_inputs(rom_type)

    # ── Romform ───────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🏠 Romform")
    st.caption("Rommål er utvendige mål. Døravstander måles fra utvendig hjørne til dørkant.")
    form_valg = st.selectbox("Form", list(FORM_MALER.keys()), key="ed_shape")
    st.caption(FORM_MALER[form_valg]["besk"])
    H_mm = st.number_input("Veggpanelhøyde (mm)", min_value=1800, max_value=8000, value=2500, step=50, key="ed_height")
    H = H_mm / 1000.0
    st.caption(f"Fri høyde over ferdig gulv: {H_mm - round(floor_depth(rom_type)*1000)} mm")

    l_shape_ok = True
    if form_valg == "L-form":
        st.caption("Den lengste vannrette og loddrette siden er totalmål. Endrer du ett delmål, beregnes det andre automatisk. Ved endring av totalmålet beholdes sist redigerte delmål.")
        defaults = [5850, 4450, 2925, 2225, 2925, 2225]
        labels = ["V1 – første vannrette side", "V2 – neste loddrette side",
                  "V3 – neste vannrette side", "V4 – neste loddrette side",
                  "V5 – siste vannrette side", "V6 – siste loddrette side"]
        for j in range(6):
            if f"l_side_{j}" not in st.session_state:
                st.session_state[f"l_side_{j}"] = defaults[j]
        previous = [st.session_state[f"l_side_{j}"] for j in range(6)]
        totals = [max(range(axis,6,2), key=lambda i: previous[i]) for axis in (0,1)]
        for j, label in enumerate(labels):
            suffix = " – totalmål" if j in totals else ""
            st.number_input(f"{label}{suffix} (mm)", min_value=100,
                            step=1, key=f"l_side_{j}", on_change=update_l_side, args=(j,previous))
        if st.session_state.get("ed_l_error"):
            st.warning(st.session_state["ed_l_error"])
        try:
            pts = l_polygon([st.session_state[f"l_side_{j}"] for j in range(6)])
            st.session_state["last_valid_l_polygon"] = pts
        except ValueError as exc:
            l_shape_ok = False
            st.error(str(exc))
            pts = st.session_state.get("last_valid_l_polygon", l_polygon(defaults))
            st.caption("Forhåndsvisningen viser siste gyldige form. Kalkulasjon og eksport venter til målene stemmer.")
        rotate_col, mirror_col, reset_col = st.columns(3)
        turns = st.session_state.get("l_turns", 0)
        mirrored = st.session_state.get("l_mirrored", False)
        if rotate_col.button("Roter 90°", key="l_rotate", help="Roter med klokken"):
            turns = (turns + 1) % 4
        if mirror_col.button("Speilvend", key="l_mirror", help="Speilvend venstre/høyre i visningen"):
            turns = (-turns) % 4
            mirrored = not mirrored
        if reset_col.button("Nullstill retning", key="l_reset"):
            turns, mirrored = 0, False
        st.session_state["l_turns"] = turns
        st.session_state["l_mirrored"] = mirrored
        pts = transform_polygon(pts, turns, mirrored)
        st.caption("Rotasjon og speiling flytter hele rommet. Hjørne-/sidenummer og målene i feltene beholdes.")
        preview, ax = plt.subplots(figsize=(5,4))
        loop = pts + [pts[0]]
        ax.fill(*zip(*pts), color="#dce8f5")
        ax.plot(*zip(*loop), color="#1a3a5c")
        for j, (x,y) in enumerate(pts):
            nx,ny = pts[(j+1)%6]
            ax.annotate(f"H{j+1}", (x,y), xytext=(5,5), textcoords="offset points", fontsize=8)
            ax.text((x+nx)/2, (y+ny)/2, f"V{j+1}", ha="center", va="center",
                    bbox=dict(facecolor="white",edgecolor="none",pad=2), fontsize=9)
        ax.set_aspect("equal"); ax.margins(.2); ax.axis("off")
        st.pyplot(preview); plt.close(preview)
    elif form_valg != "Egendefinert polygon":
        c1, c2 = st.columns(2)
        with c1:
            L_mm = st.number_input("Lengde (mm)", min_value=500, max_value=50000, value=5850, step=50, key="ed_length")
        with c2:
            B_mm = st.number_input("Bredde (mm)", min_value=500, max_value=30000, value=4450, step=50, key="ed_width")
        L_inp = L_mm / 1000.0
        B_inp = B_mm / 1000.0
        if form_valg == "Femkant – avskåret hjørne":
            cc1, cc2 = st.columns(2)
            with cc1:
                CX_mm = st.number_input("Avskjær X (mm)", min_value=50, max_value=L_mm, value=1100, step=50, key="ed_cut_x")
            with cc2:
                CY_mm = st.number_input("Avskjær Y (mm)", min_value=50, max_value=B_mm, value=1100, step=50, key="ed_cut_y")
            CX = CX_mm / 1000.0
            CY = CY_mm / 1000.0
        else:
            CX = CY = 0.0
        pts = FORM_MALER[form_valg]["func"](L_inp, B_inp, CX, CY)
    else:
        n_pts = int(st.number_input("Antall hjørner", min_value=3, max_value=16, value=5, step=1, key="ed_corners"))
        defs  = [(0,0),(5850,0),(5850,3350),(4750,4450),(0,4450)]
        pts   = []
        for i in range(n_pts):
            c1, c2 = st.columns(2)
            dx = float(defs[i][0]) if i < len(defs) else 0.0
            dy = float(defs[i][1]) if i < len(defs) else 0.0
            with c1:
                px_mm = st.number_input(f"X{i+1} (mm)", value=dx, step=50.0, key=f"px{i}")
            with c2:
                py_mm = st.number_input(f"Y{i+1} (mm)", value=dy, step=50.0, key=f"py{i}")
            pts.append((px_mm / 1000.0, py_mm / 1000.0))

    origin = st.session_state.get("ed_form_origin", [0, 0])
    pts = [(x+origin[0]/1000, y+origin[1]/1000) for x,y in pts]
    exterior_pts = list(pts)

    # Polygon-validering
    poly_ok = True
    try:
        validate_polygon(pts)
    except ValueError as e:
        st.error(f"⚠️ Ugyldig polygon: {e}")
        poly_ok = False
        st.stop()

    # ── Elementbredde ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📏 Elementbredde")
    pw_mm = st.number_input("Elementbredde (mm)", min_value=300, max_value=2000, value=1100, step=50, key="ed_panel_width")
    pw_m  = pw_mm / 1000.0

    # ── Dører med veggplassering ──────────────────────────────────────────────
    st.divider()
    st.subheader("🚪 Dører")
    nd_t = int(st.number_input("Antall dørtyper", min_value=0, max_value=4, value=1, step=1, key="ed_doors"))

    dorer_full = []   # (dk, ant, wall_idx, offset_m)  for tegninger
    dorer_mat  = []   # (dk, ant)                       for materialer/kalkulasjon
    wls_count  = len(pts)
    door_placement_ok = True
    priced_door_keys = set()

    for i in range(nd_t):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            door_options = door_keys(rom_type, DOR_DB)
            default_door = next((j for j,k in enumerate(door_options) if DOR_DB[k]["bw"]==1000 and DOR_DB[k]["bh"]==2100),0)
            dk = st.selectbox(f"Type {i+1}", door_options, index=default_door,
                              format_func=lambda k: DOR_DB[k]["label"], key=f"dt_{rom_type}_{i}")
        with c2:
            da = st.number_input("Stk", min_value=0, max_value=10, value=1, key=f"da{i}")
        with c3:
            wall_idx = st.number_input(
                "Vegg nr", min_value=1, max_value=wls_count, value=1, step=1, key=f"dw{i}"
            ) - 1
        h1, h2 = st.columns(2)
        with h1:
            offset_mm = st.number_input(
                f"Fra starthjørne til dørkant (mm) – type {i+1}", min_value=0,
                value=350, step=50, key=f"do{i}"
            )
        with h2:
            hengsel = st.selectbox(
                "Hengslingsside", ["Venstre", "Høyre"], key=f"dh{i}",
                help="Siden hengslet sitter på (sett innenfra rommet)"
            )
        if DOR_DB[dk]["pris"] == 0 and dk not in priced_door_keys:
            priced_door_keys.add(dk)
            overrides = st.session_state.setdefault("pris_override", {})
            price = st.number_input(
                f"Enhetspris for {DOR_DB[dk]['label']} (kr) – type {i+1}",
                min_value=0.0, value=float(overrides.get(f"dor_{dk}", 0)),
                step=100.0, key=f"door_price_{rom_type}_{i}_{dk}")
            overrides[f"dor_{dk}"] = price
            if price == 0 and da > 0:
                st.warning("Dørpris mangler. Døren er ikke medregnet i totalprisen før du angir pris.")
        offset_m = offset_mm / 1000.0
        wall_length = wall_lengths(pts)[int(wall_idx)]
        st.caption(f"Vegg {int(wall_idx)+1}: H{int(wall_idx)+1} → H{(int(wall_idx)+1)%wls_count+1} · {wall_length*1000:.0f} mm")
        rows = []
        for door_no in range(int(da)):
            door_width = DOR_DB[dk]["bw"] / 1000
            current_offset = offset_m + door_no*(door_width+.20)
            try:
                start, center, end, end_center = door_dimensions(wall_length, current_offset, door_width)
                rows.append({"Dør": door_no+1, "Start → kant (mm)": round(start*1000),
                             "Start → senter (mm)": round(center*1000),
                             "Slutt → kant (mm)": round(end*1000),
                             "Slutt → senter (mm)": round(end_center*1000)})
            except ValueError as exc:
                st.error(f"Dør {door_no+1}: {exc}")
                door_placement_ok = False
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True)

        dorer_full.append((dk, int(da), int(wall_idx), float(offset_m), hengsel))
        dorer_mat.append((dk, int(da)))

    # ── Åpninger (klassfronter, display-fronter etc.) ─────────────────────────
    st.divider()
    st.subheader("🪟 Åpninger / Utsparinger")
    n_ap = int(st.number_input("Antall åpninger", min_value=0, max_value=8,
                               value=0, step=1, key="n_apninger"))
    apninger_list = []   # [(wall_idx, offset_m, width_m, height_m, sill_m, label), ...]
    for ai in range(n_ap):
        st.caption(f"Åpning {ai+1}")
        ca1, ca2, ca3 = st.columns([2, 1, 1])
        with ca1:
            ap_label = st.text_input(f"Navn", value=f"Utsparing {ai+1}",
                                     key=f"ap_lbl{ai}")
        with ca2:
            ap_wall = int(st.number_input("Vegg nr", min_value=1,
                                          max_value=wls_count, value=1, step=1,
                                          key=f"ap_w{ai}")) - 1
        with ca3:
            ap_sill = st.number_input("Fra gulv (mm)", min_value=0,
                                      max_value=3000, value=0, step=50,
                                      key=f"ap_sill{ai}")
        cb1, cb2, cb3 = st.columns(3)
        with cb1:
            ap_offset_mm = st.number_input("Offset fra hjørne (mm)", min_value=50,
                                            max_value=10000, value=300, step=50,
                                            key=f"ap_off{ai}")
        with cb2:
            ap_w_mm = st.number_input("Bredde (mm)", min_value=100, max_value=5000,
                                      value=1000, step=50, key=f"ap_bw{ai}")
        with cb3:
            ap_h_mm = st.number_input("Høyde (mm)", min_value=100, max_value=3000,
                                      value=1800, step=50, key=f"ap_bh{ai}")
        apninger_list.append((
            int(ap_wall), float(ap_offset_mm) / 1000.0, float(ap_w_mm) / 1000.0,
            float(ap_h_mm) / 1000.0, float(ap_sill) / 1000.0,
            ap_label or f"Åpning {ai+1}",
        ))

    # ── Beslag ────────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🔩 Beslag")
    beslag_valg = st.multiselect(
        "Velg beslag pr. dør", list(BESLAG_DB.keys()),
        default=list(BESLAG_DB.keys())[:5], key="ed_beslag",
        format_func=lambda k: BESLAG_DB[k]["label"],
    )

    st.divider()
    bakfil = st.file_uploader("Bakgrunn plantegning PNG/JPG", type=["png","jpg","jpeg"], key=f"background_upload_{st.session_state.get('background_revision',0)}")

    # ── Prisredigering (session state) ────────────────────────────────────────
    if "pris_override" not in st.session_state:
        st.session_state["pris_override"] = {}
    with st.expander("Priser for skruer og gulvplater"):
        prices = st.session_state["pris_override"]
        prices["skruer"] = st.number_input("22 mm hvite skruer (kr/stk)", min_value=0.0, value=float(prices.get("skruer",0)), key="ed_screw_price")
        if rom_type == "Fryserom":
            prices["gulv_finer"] = st.number_input("Gulvplate 12 mm (kr/m²)", min_value=0.0, value=float(prices.get("gulv_finer",0)), key="ed_board_price")

# Convert exterior user dimensions once, before all calculations and exports.
from dimensions import inside_from_outside, corner_shift
try:
    pts = inside_from_outside(exterior_pts, pan_info.tykkelse_mm/1000)
    dorer_full = [(key, count, wall, offset-corner_shift(pts, pan_info.tykkelse_mm/1000, wall), hinge)
                  for key,count,wall,offset,hinge in dorer_full]
    apninger_list = [(wall, offset-corner_shift(pts, pan_info.tykkelse_mm/1000, wall), width, height, sill, label)
                     for wall,offset,width,height,sill,label in apninger_list]
except ValueError as exc:
    st.error(str(exc))
    st.stop()

# ── Beregning (caches dersom input ikke er endret) ────────────────────────────
import json as _json

if not poly_ok or not door_placement_ok or not l_shape_ok:
    st.error("Rett rommål eller dørplassering i sidepanelet for å fortsette.")
    st.stop()

_cache_key = dict(
    panel_key=panel_key, rom_type=rom_type,
    pts_tuple=tuple(tuple(p) for p in pts),
    H=H, pw_m=pw_m,
    dorer_tuple=tuple(tuple(d) for d in dorer_full),
    beslag_tuple=tuple(beslag_valg),
    navn=navn, pnr=pnr, tnr=tnr, dato=dato, maalestokk=maalestokk,
    pris_json=_json.dumps(st.session_state["pris_override"], sort_keys=True),
    breeam_mult=1.0,
    apninger_tuple=tuple(tuple(a) for a in apninger_list) if apninger_list else (),
)
try:
    result = _beregn_cached(**_cache_key)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
fdv_df   = lag_fdv_oversikt(panel_key, rom_type, dorer_mat, beslag_valg)

# ProjectInput med full dorer_full (for tegninger)
inp = ProjectInput(
    navn, pnr, tnr, dato, maalestokk, rom_type, panel_key,
    pts, H, pw_m, dorer_full, beslag_valg,
    apninger=apninger_list if apninger_list else [],
)

# Portable room snapshot includes only project data, never secrets or chat history.
form_data = {"dimension_basis":"external", "origin_mm":origin, "waste_pct":10,"panel_kg_m2":0,"panel_stock_mm":0,"kind": form_valg, "plywood_width_mm": st.session_state.get("ed_finer_width",1500), "plywood_length_mm": st.session_state.get("ed_finer_length",3000)}
form_data["accessory_quantities"] = {key: st.session_state.get(f"ed_accessory_{key}", 0) or None
                                     for key in ("fugemasse", "skum", "pakninger", "alarm")}
form_data["thermal"] = thermal_data
if form_valg == "L-form":
    form_data.update(sides_mm=[st.session_state[f"l_side_{j}"] for j in range(6)],
                     turns=st.session_state.get("l_turns",0), mirrored=st.session_state.get("l_mirrored",False))
elif form_valg == "Egendefinert polygon":
    form_data["points_mm"] = [[(x-origin[0]/1000)*1000,(y-origin[1]/1000)*1000] for x,y in exterior_pts]
else:
    form_data.update(length_mm=L_mm,width_mm=B_mm)
    if form_valg == "Femkant – avskåret hjørne":
        form_data.update(cut_x_mm=CX_mm,cut_y_mm=CY_mm)
try:
    current_room = capture_room(inp,form_data,bakfil)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
if modul == "Montasjetegninger":
    if st.session_state.get("_forrige_modul") != "Montasjetegninger":
        st.session_state["ed_drawing_walls"] = list(current_room["excluded_walls"])
    selected_walls = st.multiselect("Vegger som skal utelates i montasjetegninger",list(range(len(inp.pts))),
        default=current_room["excluded_walls"],format_func=lambda i:f"V{i+1}",key="ed_drawing_walls")
    current_room["excluded_walls"] = list(selected_walls)
    for saved in st.session_state["project_rooms"]:
        if saved["id"] == current_room["id"]:
            saved["excluded_walls"] = list(selected_walls)
            st.session_state.pop(f"omit_{saved['id']}",None)
    st.session_state["last_valid_editor"] = current_room
from dataclasses import replace
inp = replace(inp, excluded_walls=tuple(current_room["excluded_walls"]))
result = beregn_prosjekt(inp,pris_override=st.session_state["pris_override"])
room_controls(current_room)
if bakfil is None and current_room.get("background"):
    bakfil = io.BytesIO(base64.b64decode(current_room["background"]["data"]))

# ── Hoved-header ──────────────────────────────────────────────────────────────
st.title(f"❄️ {navn.strip() or 'Kjølerom'}")
st.caption(
    f"{rom_type} · Panel: {result['panel']['label']} · Elementbredde: {pw_mm} mm · Versjon 2026.10.26-r08"
)
st.divider()

# ══ MODULER ═══════════════════════════════════════════════════════════════════
if modul == "Kalkulasjon" and result.get("missing_prices"):
    st.warning("Ufullstendig prisgrunnlag. Kostnaden er bare en delsum. Mangler pris: " + "; ".join(result["missing_prices"]))

if modul == "Rom og sammenstilling":
    assembly_ui()

elif modul == "Kalkulasjon":
    st.header("📦 Kalkulasjon")
    from cutlist_pdf import project_materials
    from geometry import poly_area
    cuts = result["df_kapp"]
    areas = pd.to_numeric(cuts.Areal_m2, errors="coerce")
    metrics = [("Veggareal", areas[cuts.Vegg.str.startswith("Vegg ")].sum(), "m²"),
               ("Takareal", areas[cuts.Vegg.eq("Tak")].sum(), "m²")]
    if rom_type == "Fryserom":
        metrics.extend([("Gulvpanel", areas[cuts.Type.str.startswith("Gulv PIR")].sum(), "m²"),
                        ("Gulvplater", poly_area(inp.pts), "m²")])
    materials = project_materials([current_room])
    metrics.append(("Beslag", materials.loc[materials.Gruppe.eq("Beslag"), "Løpemeter"].sum(), "LM"))
    for column, (label, value, unit) in zip(st.columns(len(metrics)), metrics):
        with column:
            card(label, f"{value:.2f} {unit}".replace(".", ","))
    st.subheader("Materialliste")
    st.dataframe(result["df_mat"].drop(columns=["CO₂ (kg)", "NS3420"], errors="ignore"), use_container_width=True, hide_index=True)
    st.download_button(
        "Last ned materialliste CSV",
        result["df_mat"].drop(columns=["NS3420"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
        f"{navn or 'prosjekt'}_materialliste.csv", "text/csv",
    )
    with st.expander("U-verdi og varmetap"):
        thermal_ui(current_room, st.session_state["project_rooms"])

elif modul == "FDV":
    st.header("🗂️ FDV")
    st.markdown(lag_fdv_tekst(navn, panel_key, rom_type))
    st.subheader("FDV-oversikt")
    st.dataframe(fdv_df, use_container_width=True, hide_index=True)
    st.download_button(
        "Last ned FDV CSV",
        fdv_df.to_csv(index=False).encode("utf-8-sig"),
        f"{navn or 'prosjekt'}_fdv.csv", "text/csv",
    )
    try:
        fdv_scope = st.radio("FDV for", ["Dette rommet", "Hele prosjektet"], horizontal=True)
        selected_fdv = st.session_state["project_rooms"] if fdv_scope == "Hele prosjektet" else [current_room]
        selected_fdv = [r for r in selected_fdv if r["id"] != current_room["id"]] + [current_room]
        if any(not r["input"]["panel_key"].startswith("PIR") for r in selected_fdv):
            raise ValueError("Standardpakken dokumenterer BALEX PIR STANDARD. Velg riktig leverandørdokumentasjon for andre paneltyper.")
        pdf = lag_standard_fdv_pdf(navn or "Prosjekt", pnr,
                                  tuple(r["input"]["navn"] for r in selected_fdv))
        st.download_button(
            "Last ned standard FDV PDF", pdf,
            f"{navn or 'prosjekt'}_fdv.pdf", "application/pdf",
        )
    except Exception as exc:
        st.info(str(exc))

elif modul == "Montasjetegninger":
    st.header("📐 Montasjetegninger")
    retained_walls = [i for i in range(len(inp.pts)) if i not in inp.excluded_walls]
    if not retained_walls:
        st.info("Alle vegger er utelatt. Behold minst én vegg for å vise snitt og veggoppstalter.")
        st.stop()
    tab_plan, tab_snitt, tab_tak, tab_oppsalt, tab_prod, tab_3d = st.tabs(
        ["Plantegning", "Snitt", "Taktegning", "Vegger", "Produksjonstegninger", "3D"]
    )

    with tab_plan:
        fig = tegn_plantegning(inp, result, bakfil, apninger=apninger_list or None)
        st.pyplot(fig, use_container_width=True)
        pdf = figur_som_pdf(fig)
        plt.close(fig)
        st.download_button(
            "Last ned plantegning PDF", pdf,
            f"{tnr}_{navn or 'prosjekt'}_plan.pdf", "application/pdf",
        )
        wall_orders = panel_order_rows(result["df_kapp"], H_mm, pw_mm)
        vdf = pd.DataFrame([{
            "Vegg": f"V{i+1}", "Utvendig lengde (m)": round(w, 3),
            "Utvendig lengde (mm)": round(w*1000),
            "Antall elementer": int(wall_orders.Vegg.eq(f"Vegg {i+1}").sum()),
        } for i, w in enumerate(wall_lengths(exterior_pts))])
        st.dataframe(vdf, use_container_width=True, hide_index=True)

    with tab_snitt:
        wls = wall_lengths(exterior_pts)
        vegg_options = [f"Vegg {i+1}  ({wls[i]*1000:.0f} mm)" for i in retained_walls]
        valgt  = st.selectbox("Velg snitt-vegg", vegg_options)
        v_idx  = retained_walls[vegg_options.index(valgt)]
        seksjon = st.text_input("Seksjon", "A-A")
        fig = tegn_snitt(inp, result, v_idx, seksjon, apninger=apninger_list or None)
        st.pyplot(fig, use_container_width=True)
        pdf = figur_som_pdf(fig)
        plt.close(fig)
        st.download_button(
            "Last ned snitt PDF", pdf,
            f"{tnr}_{navn or 'prosjekt'}_snitt_{seksjon}.pdf", "application/pdf",
        )

    with tab_tak:
        st.info(
            "Taktegning viser alle takelementer sett ovenfra med bredde-mål, "
            "romvinkler og spennretning. "
            + ("Fryserom: gulvpanel vises i eget diagram." if "Fryserom" in rom_type else "")
        )
        fig_tak = tegn_taktegning(inp, result)
        st.pyplot(fig_tak, use_container_width=True)
        pdf_tak = figur_som_pdf(fig_tak)
        plt.close(fig_tak)
        st.download_button(
            "Last ned taktegning PDF", pdf_tak,
            f"{tnr}_{navn or 'prosjekt'}_tak.pdf", "application/pdf",
        )

    with tab_oppsalt:
        st.info("Vegger viser panelfordeling og dørplassering på én vegg.")
        wls2 = wall_lengths(pts)
        v_opts2 = [f"Vegg {i+1}  ({wls2[i]*1000:.0f} mm)" for i in retained_walls]
        valgt2 = st.selectbox("Velg vegg", v_opts2, key="oppstalt_vegg")
        v_idx2 = retained_walls[v_opts2.index(valgt2)]
        fig2 = tegn_veggoppstaltt(inp, result, v_idx2, apninger=apninger_list or None)
        st.pyplot(fig2, use_container_width=True)
        pdf2 = figur_som_pdf(fig2)
        plt.close(fig2)
        st.download_button(
            "Last ned veggoppstalt PDF", pdf2,
            f"{tnr}_{navn or 'prosjekt'}_vegg{v_idx2+1}.pdf", "application/pdf",
        )

    with tab_prod:
        vis_bare_tilpassede = st.checkbox(
            "Vis kun tilpassede elementer (kapp, start, skrå)",
            value=False,
            key="prod_bare_tilpassede",
        )
        figs_prod = tegn_produksjonsfigurer(inp, result, bare_tilpassede=vis_bare_tilpassede)
        if not figs_prod:
            st.warning("Ingen elementer å vise. Prøv å fjerne filteret.")
        else:
            samlet_pdf = figurer_som_samlet_pdf(figs_prod)
            st.download_button(
                "Last ned alle produksjonstegninger PDF",
                samlet_pdf,
                f"{tnr}_{navn or 'prosjekt'}_produksjon_alle.pdf",
                "application/pdf",
                key="dl_prod_alle",
            )
        for pi, fp in enumerate(figs_prod):
            st.pyplot(fp, use_container_width=True)
            pdf_p = figur_som_pdf(fp)
            plt.close(fp)
            st.download_button(
                f"Last ned side {pi+1} PDF", pdf_p,
                f"{tnr}_{navn or 'prosjekt'}_produksjon_s{pi+1}.pdf", "application/pdf",
                key=f"dl_prod_{pi}",
            )

    with tab_3d:
        # Kameraretningen justeres direkte i 3D-visningen (dra med musen),
        # så egne rotasjon/høydevinkel-slidere er ikke nødvendig.
        fig3 = tegn_3d_modell(inp, apninger=apninger_list or None)
        if st.button("Rett opp / nullstill 3D",key="reset_room_camera"):
            st.session_state["room_camera_revision"] = st.session_state.get("room_camera_revision",0)+1
        fig3.update_layout(uirevision=st.session_state.get("room_camera_revision",0))
        st.plotly_chart(fig3, use_container_width=True,config=dict(modeBarButtonsToRemove=["orbitRotation"]))
        html_str = fig3.to_html(include_plotlyjs=True)
        _logo_uri = logo_data_uri()
        if _logo_uri and "<body>" in html_str:
            html_str = html_str.replace(
                "<body>",
                "<body><img src='" + _logo_uri + "' "
                "style='position:fixed;top:12px;left:12px;height:40px;z-index:1000;'>",
                1,
            )
        html = html_str.encode("utf-8")
        st.download_button(
            "Last ned interaktiv 3D HTML", html,
            f"{tnr}_{navn or 'prosjekt'}_3d.html", "text/html",
        )
        ifc_3d = gen_ifc(
            pts, H, navn or "Kjolerom", panel_key,
            dorer_full, rom_type, pw_m,
            apninger=apninger_list if apninger_list else None,
            excluded_walls=inp.excluded_walls,
        )
        st.download_button(
            "Last ned IFC", ifc_3d,
            f"{tnr}_{navn or 'prosjekt'}.ifc", "application/octet-stream",
            key="dl_ifc_3d",
        )

elif modul == "Transport":
    from transport import transport_ui
    transport_ui(st.session_state["project_rooms"] or [current_room])

elif modul == "Elementer":
    st.header("Elementer")
    sam = result["sam"]
    c1, c2, c3 = st.columns(3)
    with c1: st.info(f"Veggelementer: {sam['tot_panel']} stk")
    with c2: st.info(f"Takelementer: {sam['tak']} stk")
    with c3: st.info(f"Gulvelementer: {sam['gulv']} stk" if "Fryserom" in rom_type else "Kjølerom: ingen gulvpanel")
    from purchase_summary import element_cutlist, panel_summary_ui
    cut_export = element_cutlist([current_room])
    st.dataframe(cut_export, use_container_width=True, hide_index=True)
    st.download_button(
        "Last ned kappliste CSV",
        cut_export.to_csv(index=False).encode("utf-8-sig"),
        f"{navn or 'prosjekt'}_kappliste.csv", "text/csv",
    )

    panel_summary_ui([current_room])

finishing_ui(st.session_state["project_rooms"] if modul == "Rom og sammenstilling" else [current_room])
from cutlist_pdf import pdf_downloads, material_downloads
if modul in ("Elementer", "Rom og sammenstilling"):
    export_rooms = st.session_state["project_rooms"] if modul == "Rom og sammenstilling" else [current_room]
    if modul == "Rom og sammenstilling" and export_rooms:
        export_options = ["Alle rom"] + [r["id"] for r in export_rooms]
        export_labels = {r["id"]: f"{i+1}. {r['input']['navn'] or r['input']['rom_type']}" for i,r in enumerate(export_rooms)}
        if st.session_state.get("export_room_choice") not in export_options:
            st.session_state["export_room_choice"] = "Alle rom"
        export_choice = st.selectbox("Last ned for rom", export_options,
            format_func=lambda value: export_labels.get(value,value), key="export_room_choice")
        if export_choice != "Alle rom":
            export_rooms = [r for r in export_rooms if r["id"] == export_choice]
        st.caption("Valget gjelder PDF-kapplister og materiallisten nedenfor. Utelatte fellesvegger beholdes utelatt også ved nedlasting av ett rom.")
        material_downloads(export_rooms, all_rooms=export_choice == "Alle rom")
    pdf_downloads(export_rooms)
project_download(current_room)

st.markdown("---")
st.caption("Stramo kjøleromssystem · kalkulasjon, FDV, montasje, kapplister og IFC")

st.session_state["_forrige_modul"] = modul
