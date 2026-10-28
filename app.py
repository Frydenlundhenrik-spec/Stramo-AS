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
from export_pdf import lag_enkel_pdf, lag_tilbuds_pdf
from project_ui import (prepare_project, upload_project, capture_room, room_bar, add_room_button, project_download, assembly_ui, finishing_ui)
from oversikt import oversikt_ui, kpi, kpi_rad, tall
from html import escape as html_escape
from branding import LOGO_PATH, logo_finnes, logo_data_uri
from thermal_ui import thermal_inputs, thermal_ui

st.set_page_config(
    page_title="Stramo AS",
    page_icon=str(LOGO_PATH) if logo_finnes() else "❄️",
    layout="wide",
)

from login import require_login
require_login()

prepare_project()

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
  :root{--s-bla:#0d3b54;--s-gul:#e3e011;--s-linje:#dde3e9;--s-dempet:#66788a;--s-bg:#f4f6f8;}
  html,body,[class*="css"]{font-family:'Inter',sans-serif;}
  .stApp{background:var(--s-bg);}
  header[data-testid="stHeader"]{background:transparent;}
  .block-container{padding:1.6rem 2rem 2rem 2rem;max-width:none;}
  h1,h2,h3{color:var(--s-bla);}

  /* Sidepanel og meny */
  section[data-testid="stSidebar"]{background:var(--s-bla);}
  section[data-testid="stSidebar"] hr{border-color:rgba(255,255,255,.15);}
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"]{color:rgba(255,255,255,.55);}
  .s-logo{background:#fff;border-radius:10px;padding:12px;text-align:center;margin-bottom:6px;}
  .s-logo img{height:46px;}
  section[data-testid="stSidebar"] [role="radiogroup"]{gap:2px;width:100%;}
  section[data-testid="stSidebar"] [role="radiogroup"] > *{width:100%;}
  section[data-testid="stSidebar"] .stElementContainer:has([role="radiogroup"]),
  section[data-testid="stSidebar"] [data-testid="stRadio"]{width:100%!important;}
  section[data-testid="stSidebar"] [role="radiogroup"] label{width:100%;padding:9px 12px;border-radius:8px;margin:0;}
  /* Skjul radioknappens sirkel (alt i etiketten som ikke er selve teksten). */
  section[data-testid="stSidebar"] [role="radiogroup"] label div:not([data-testid="stMarkdownContainer"]):not(:has([data-testid="stMarkdownContainer"])):not([data-testid="stMarkdownContainer"] *){display:none;}
  .st-key-meny_minimer{align-items:flex-end;}
  .st-key-meny_minimer button{color:rgba(255,255,255,.75);min-height:0;padding:2px 6px;}
  .st-key-meny_minimer button:hover{color:#fff;}
  section[data-testid="stSidebar"] [role="radiogroup"] label p{color:rgba(255,255,255,.8);font-size:15px;display:flex;align-items:center;gap:10px;}
  section[data-testid="stSidebar"] [role="radiogroup"] label p::before{font-family:"Material Symbols Rounded";font-size:20px;font-weight:400;line-height:1;}
  section[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:rgba(255,255,255,.07);}
  section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){background:rgba(255,255,255,.13);box-shadow:inset 3px 0 0 var(--s-gul);}
  section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p{color:#fff;font-weight:600;}
  section[data-testid="stSidebar"] [data-testid="stExpander"] details{background:#fff;border-radius:8px;}
  section[data-testid="stSidebar"] .stDownloadButton button{background:var(--s-gul);color:var(--s-bla);}
  section[data-testid="stSidebar"] .stDownloadButton button:hover{background:#cfcc0c;color:var(--s-bla);}

  /* Knapper */
  .stButton button,.stDownloadButton button{border-radius:8px;font-weight:600;}
  .stButton button[kind="primary"],.stDownloadButton button{border:none;background:var(--s-bla);color:#fff;}
  .stButton button[kind="primary"]:hover,.stDownloadButton button:hover{background:#0a2d40;color:#fff;}

  /* Toppfelt og nøkkeltall */
  .s-sti{color:var(--s-dempet);font-size:13px;}
  .s-tittel{color:var(--s-bla);font-size:26px;font-weight:700;line-height:1.25;margin-bottom:14px;}
  .s-kpi-rad{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:12px;margin-bottom:18px;}
  .s-kpi{background:#fff;border:1px solid var(--s-linje);border-left:4px solid var(--s-bla);border-radius:10px;padding:11px 16px;}
  .s-kpi.gul{border-left-color:var(--s-gul);}
  .s-kpi-etikett{font-size:12px;color:var(--s-dempet);}
  .s-kpi-verdi{font-size:22px;font-weight:700;color:var(--s-bla);white-space:nowrap;}
  .s-kpi-verdi small{font-size:13px;color:var(--s-dempet);font-weight:500;}
  @media (max-width:1100px){.s-kpi-rad{grid-template-columns:repeat(2,minmax(0,1fr));}}

  /* Inndatapanel */
  .st-key-inndata{background:#fff;border:1px solid var(--s-linje);border-radius:12px;padding:14px 14px 8px;}
  .st-key-inndata [data-testid="stExpander"] details{border:none;border-top:1px solid var(--s-linje);border-radius:0;}
  .st-key-inndata [data-testid="stExpander"] summary p{font-weight:600;font-size:15px;color:var(--s-bla);}
  .st-key-skjult_inndata{display:none!important;}
  .st-key-inndata_veksle button{color:var(--s-bla);min-height:0;padding:2px 6px;}
  div[data-testid="stColumn"]:has(.st-key-tegning_folger){position:sticky;top:3.75rem;align-self:flex-start;}

  /* Prosjektoversikt */
  .s-seksjon-tittel{font-size:17px;font-weight:700;color:var(--s-bla);margin:20px 0 10px;}
  div[class*="st-key-romkort_"]{background:#fff;}
  .s-romkort-bilde{background:#f6f8fa;border-radius:8px;display:flex;justify-content:center;padding:8px;margin-bottom:10px;}
  .s-romkort-tittel{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:16px;color:#1b2733;}
  .s-romkort-info{color:var(--s-dempet);font-size:12.5px;margin:4px 0 10px;}
  .s-romkort-tall{display:flex;gap:16px;font-size:12.5px;color:var(--s-dempet);}
  .s-romkort-tall b{color:var(--s-bla);font-size:15px;}
  .s-merke{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap;}
  .s-merke.ok{background:#e3f4ec;color:#2e9e6b;}
  .s-merke.varsel{background:#fbf0dc;color:#b8730f;}
  .s-merke.bla{background:#e8f0f5;color:var(--s-bla);}
  .st-key-romkort_nytt{background:transparent!important;border-style:dashed!important;}
  .s-nytt-rom{text-align:center;color:var(--s-bla);font-size:34px;line-height:1.1;padding:24px 0 10px;}
  .s-nytt-rom span{font-size:15px;font-weight:600;}

  .card{background:#fff;padding:14px 18px;border-radius:12px;
    border:1px solid #d1e3f5;box-shadow:0 2px 6px rgba(0,0,0,.05);margin-bottom:.7rem;}
  .ct{font-size:12px;font-weight:600;color:#6b7280;margin-bottom:3px;}
  .cv{font-size:22px;font-weight:700;color:#1a3a5c;}
  .cs{font-size:11px;color:#9ca3af;}
  /* Streamlit tables include their own CSV export button. */
  button[aria-label="Download as CSV"]{display:none!important;}
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
    plywood_width_mm: int = 1500, plywood_length_mm: int = 3000,
) -> dict[str, Any]:
    import json
    pris_override = json.loads(pris_json) if pris_json else {}
    dorer_mat = list(dorer_tuple)
    inp = ProjectInput(
        navn, pnr, tnr, dato, maalestokk, rom_type, panel_key,
        list(pts_tuple), H, pw_m, dorer_mat, list(beslag_tuple),
        apninger=list(apninger_tuple),
        plywood_width_mm=plywood_width_mm, plywood_length_mm=plywood_length_mm,
    )
    return beregn_prosjekt(inp, pris_override=pris_override, breeam_multiplier=breeam_mult)


# ── Navigasjon og sideoppsett ─────────────────────────────────────────────────
MODULER = ["Oversikt", "Rom", "Tegninger", "Kalkulasjon", "Elementer",
           "FDV", "Transport", "Sammenstilling"]
# Menyikoner (Material Symbols) i samme rekkefølge som MODULER; tegnes med CSS.
MODUL_IKON = ["dashboard", "edit_square", "architecture", "calculate", "view_column",
              "description", "local_shipping", "join_inner"]
# Sidene der inndatapanelet vises ved siden av innholdet.
INNDATA_MODULER = {"Rom", "Tegninger"}
# Sidene som gjelder hele prosjektet, ikke rommet som er åpent.
PROSJEKT_MODULER = {"Oversikt", "Transport", "Sammenstilling"}

# Keep an open session on the calculation page after removing the old menu item.
_GAMLE_MODULER = {"U-verdi og varmetap": "Kalkulasjon", "Montasjetegninger": "Tegninger",
                  "Rom og sammenstilling": "Sammenstilling"}
if st.session_state.get("ed_module") in _GAMLE_MODULER:
    st.session_state["ed_module"] = _GAMLE_MODULER[st.session_state["ed_module"]]

def _bytt_menystorrelse():
    st.session_state["meny_minimert"] = not st.session_state.get("meny_minimert", False)


_minimert = st.session_state.get("meny_minimert", False)
with st.sidebar:
    st.button("Utvid meny" if _minimert else "Minimer meny", key="meny_minimer", type="tertiary",
              icon=":material/left_panel_open:" if _minimert else ":material/left_panel_close:",
              on_click=_bytt_menystorrelse, help="Vis eller skjul tekstene i menyen")
    _logo_uri = logo_data_uri()
    if _logo_uri:
        st.markdown(f'<div class="s-logo"><img src="{_logo_uri}" alt="Stramo"></div>', unsafe_allow_html=True)
    else:
        st.title("Stramo")
    modul = st.radio("Meny", MODULER, key="ed_module", label_visibility="collapsed")
    st.markdown("<style>" + "".join(
        f'section[data-testid="stSidebar"] [role="radiogroup"] > :nth-child({i}) p::before{{content:"{ikon}";}}'
        for i, ikon in enumerate(MODUL_IKON, 1)) + "</style>", unsafe_allow_html=True)
    if _minimert:
        # Smal ikonlist: bare ikonene i menyen vises.
        st.markdown("""<style>
          section[data-testid="stSidebar"]{width:88px!important;min-width:88px!important;max-width:88px!important;}
          section[data-testid="stSidebar"] > div{width:88px!important;}
          [data-testid="stSidebarUserContent"]{padding-left:10px!important;padding-right:10px!important;}
          [data-testid="stSidebarResizeHandle"],.st-key-meny_ekstra{display:none!important;}
          section[data-testid="stSidebar"] [role="radiogroup"] label{padding:10px 0;justify-content:center;}
          section[data-testid="stSidebar"] [role="radiogroup"] label p{font-size:0!important;justify-content:center;gap:0;}
          section[data-testid="stSidebar"] [role="radiogroup"] label p::before{font-size:24px;}
          .st-key-meny_minimer button p{display:none;}
          section[data-testid="stSidebar"] .stElementContainer:has(.s-logo){display:none!important;}
        </style>""", unsafe_allow_html=True)
    with st.container(key="meny_ekstra"):
        st.divider()
        upload_project()
        lagre_plass = st.container()
        st.caption("Stramo kjøleromssystem · versjon 2026.10.27-r11")

topp = st.container()
def _bytt_inndatapanel():
    st.session_state["inndata_minimert"] = not st.session_state.get("inndata_minimert", False)


_inndata_minimert = st.session_state.get("inndata_minimert", False)
if modul in INNDATA_MODULER and not _inndata_minimert:
    _venstre, innhold = st.columns([1.25, 2.4], gap="large")
    inndata_kol = _venstre.container(key="inndata")
    with inndata_kol:
        st.button("Skjul inndata", key="inndata_veksle", type="tertiary", icon=":material/left_panel_close:",
                  on_click=_bytt_inndatapanel, help="Skjul inndatapanelet og gi tegningen hele bredden")
else:
    innhold = st.container()
    if modul in INNDATA_MODULER:
        with innhold:
            st.button("Vis inndata", key="inndata_veksle", type="tertiary", icon=":material/left_panel_open:",
                      on_click=_bytt_inndatapanel, help="Vis inndatapanelet igjen")
    # Inndata må tegnes på hver side for at verdiene skal beholdes; her skjules panelet.
    inndata_kol = st.container(key="skjult_inndata")

oversikt_viste_utkast = None
if modul == "Oversikt":
    with innhold:
        oversikt_viste_utkast = oversikt_ui()
with inndata_kol:
    room_bar()
    legg_til_plass = st.container()
    with st.expander(':material/badge: Prosjektinfo', expanded=False):
        navn        = st.text_input("Romnavn / prosjektnavn", st.session_state.get("navn", ""), key="ed_name",
                                     placeholder="Skriv inn prosjektnavn...")
        pnr         = st.text_input("Prosjektnr", st.session_state.get("pnr", "1001"), key="ed_pnr")
        tnr         = st.text_input("Tegningsnr", st.session_state.get("tnr", "A101"), key="ed_tnr")
        dato        = st.text_input("Dato", st.session_state.get("dato", datetime.today().strftime("%d.%m.%Y")), key="ed_date")
        maalestokk = "Ikke målfast"
        st.caption("Målestokk: Ikke målfast – bruk påførte mål.")
    with st.expander(':material/ac_unit: Romtype og panel', expanded=True):
        rom_type = st.radio("Romtype", ["Kjølerom", "Fryserom"], key="ed_room_type", horizontal=True)

        if rom_type == "Fryserom":
            st.caption("22 mm lekter → gulvpanel som vegg/tak → vegger på gulvpanel → 12 mm gulvplate innenfor vegger.")
            g1, g2 = st.columns(2)
            g1.number_input("Gulvplate bredde (mm)",min_value=100,max_value=10000,value=1500,key="ed_finer_width")
            g2.number_input("Gulvplate lengde (mm)",min_value=100,max_value=10000,value=3000,key="ed_finer_length")
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
        st.caption(
            f"U-verdi {pan_info.u_verdi} W/m²K · CO₂ {pan_info.co2_kg_m2} kg/m² · {pan_info.pris_nok_m2} kr/m²  \n"
            f"Automatisk panelvekt: {estimated_panel_weight(panel_key):g} kg/m² · "
            + ("Balex produktdatablad" if panel_key in BALEX_WEIGHTS else "ESTIMAT")
        )
        st.caption("Beslag: 10 % svinn/kapp, avrundet opp til hele 2500 mm lengder. Ingen prosentvis kapptillegg på paneler eller gulvplater. "
                   "Tilbehør beregnes fra elementflater, gulvplater, vegghjørner og dører.")
        if panel_key not in _documented_panels:
            st.caption("U-verdien over er en eldre katalogverdi uten tilhørende produktdokumentasjon. Oppgi dokumentert U-verdi i varmeberegningen før den brukes der.")
    thermal_data = thermal_inputs(rom_type)
    with st.expander(':material/square_foot: Romform og mål', expanded=True):
        st.caption("Rommål er utvendige mål. Døravstander måles fra utvendig hjørne til dørkant.")
        form_valg = st.selectbox("Form", list(FORM_MALER.keys()), key="ed_shape")
        st.caption(FORM_MALER[form_valg]["besk"])
        hk, bk = st.columns(2)
        H_mm = hk.number_input("Veggpanelhøyde (mm)", min_value=1800, max_value=8000, value=2500, step=50, key="ed_height")
        H = H_mm / 1000.0
        pw_mm = bk.number_input("Elementbredde (mm)", min_value=300, max_value=2000, value=1100, step=50, key="ed_panel_width")
        pw_m  = pw_mm / 1000.0
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
            innhold.error(f"Ugyldig romform: {e}. Rett målene under «Romform og mål».")
            poly_ok = False
            st.stop()
    with st.expander(':material/door_front: Dører', expanded=True):
        nd_t = int(st.number_input("Antall dørtyper", min_value=0, max_value=4, value=1, step=1, key="ed_doors"))

        dorer_full = []   # (dk, ant, wall_idx, offset_m)  for tegninger
        dorer_mat  = []   # (dk, ant)                       for materialer/kalkulasjon
        wls_count  = len(pts)
        door_placement_ok = True
        priced_door_keys = set()

        for i in range(nd_t):
            st.markdown(f"**Dørtype {i+1}**")
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
            if dk not in priced_door_keys:
                priced_door_keys.add(dk)
                overrides = st.session_state.setdefault("pris_override", {})
                price = st.number_input(
                    f"Enhetspris for {DOR_DB[dk]['label']} (kr) – type {i+1}",
                    min_value=0.0, value=float(overrides.get(f"dor_{dk}", DOR_DB[dk]["pris"])),
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
    with st.expander(':material/crop_free: Åpninger og utsparinger', expanded=False):
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
    with st.expander(':material/hardware: Beslag', expanded=False):
        beslag_valg = st.multiselect(
            "Velg beslag pr. dør", list(BESLAG_DB.keys()),
            default=list(BESLAG_DB.keys())[:5], key="ed_beslag",
            format_func=lambda k: BESLAG_DB[k]["label"],
        )
    with st.expander(':material/sell: Priser og bakgrunnsbilde', expanded=False):
        bakfil = st.file_uploader("Bakgrunn plantegning PNG/JPG", type=["png","jpg","jpeg"], key=f"background_upload_{st.session_state.get('background_revision',0)}")

        # ── Prisredigering (session state) ────────────────────────────────────────
        if "pris_override" not in st.session_state:
            st.session_state["pris_override"] = {}
        prices = st.session_state["pris_override"]
        from accessories import CATALOG
        for key, (label, unit, default, _) in CATALOG.items():
            if rom_type != "Fryserom" and key not in ("skruer_eske", "silikon_hvit"):
                continue
            prices[key] = st.number_input(f"{label} (kr/{unit})", min_value=0.0,
                value=float(prices.get(key, default)), key=f"ed_price_{key}")
        if rom_type == "Fryserom":
            prices["gulv_finer"] = st.number_input("Gulvplate 12 mm (kr/m² bestilt plate)", min_value=0.0, value=float(prices.get("gulv_finer",1000)), key="ed_board_price")

# Convert exterior user dimensions once, before all calculations and exports.
from dimensions import inside_from_outside, corner_shift
try:
    pts = inside_from_outside(exterior_pts, pan_info.tykkelse_mm/1000)
    dorer_full = [(key, count, wall, offset-corner_shift(pts, pan_info.tykkelse_mm/1000, wall), hinge)
                  for key,count,wall,offset,hinge in dorer_full]
    apninger_list = [(wall, offset-corner_shift(pts, pan_info.tykkelse_mm/1000, wall), width, height, sill, label)
                     for wall,offset,width,height,sill,label in apninger_list]
except ValueError as exc:
    innhold.error(str(exc))
    st.stop()

# ── Beregning (caches dersom input ikke er endret) ────────────────────────────
import json as _json

if not poly_ok or not door_placement_ok or not l_shape_ok:
    innhold.error("Rett rommål eller dørplassering i inndatapanelet (siden «Rom») for å fortsette.")
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
    plywood_width_mm=st.session_state.get("ed_finer_width",1500),
    plywood_length_mm=st.session_state.get("ed_finer_length",3000),
)
try:
    result = _beregn_cached(**_cache_key)
except ValueError as exc:
    innhold.error(str(exc))
    st.stop()
fdv_df   = lag_fdv_oversikt(panel_key, rom_type, dorer_mat, beslag_valg)

# ProjectInput med full dorer_full (for tegninger)
inp = ProjectInput(
    navn, pnr, tnr, dato, maalestokk, rom_type, panel_key,
    pts, H, pw_m, dorer_full, beslag_valg,
    apninger=apninger_list if apninger_list else [],
    plywood_width_mm=st.session_state.get("ed_finer_width",1500),
    plywood_length_mm=st.session_state.get("ed_finer_length",3000),
)

# Portable room snapshot includes only project data, never secrets or chat history.
form_data = {"dimension_basis":"external", "origin_mm":origin, "waste_pct":10,"panel_kg_m2":0,"panel_stock_mm":0,"kind": form_valg, "plywood_width_mm": st.session_state.get("ed_finer_width",1500), "plywood_length_mm": st.session_state.get("ed_finer_length",3000)}
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
    innhold.error(str(exc))
    st.stop()
with innhold:
    if modul == "Tegninger":
        if st.session_state.get("_forrige_modul") != "Tegninger":
            st.session_state["ed_drawing_walls"] = list(current_room["excluded_walls"])
        st.session_state.setdefault("ed_drawing_walls", list(current_room["excluded_walls"]))
        selected_walls = st.multiselect("Vegger som skal utelates i montasjetegninger",list(range(len(inp.pts))),
            format_func=lambda i:f"V{i+1}",key="ed_drawing_walls",placeholder="Ingen – alle vegger tegnes")
        current_room["excluded_walls"] = list(selected_walls)
        for saved in st.session_state["project_rooms"]:
            if saved["id"] == current_room["id"]:
                saved["excluded_walls"] = list(selected_walls)
                st.session_state.pop(f"omit_{saved['id']}",None)
        st.session_state["last_valid_editor"] = current_room
from dataclasses import replace
inp = replace(inp, excluded_walls=tuple(current_room["excluded_walls"]))
result = beregn_prosjekt(inp,pris_override=st.session_state["pris_override"])
with legg_til_plass:
    add_room_button(current_room)
if bakfil is None and current_room.get("background"):
    bakfil = io.BytesIO(base64.b64decode(current_room["background"]["data"]))

# ── Toppfelt med nøkkeltall ───────────────────────────────────────────────────
with topp:
    _rom_navn = html_escape(navn.strip() or rom_type)
    if modul in PROSJEKT_MODULER:
        _antall = len(st.session_state["project_rooms"])
        _tittel = f"Prosjekt {html_escape(pnr)}"
        _under = f"{_antall} rom i prosjektet · åpent rom: {_rom_navn}"
    else:
        _tittel = _rom_navn
        _under = (f"Prosjekt {html_escape(pnr)} · {rom_type} · {result['panel']['label']} · "
                  f"elementbredde {pw_mm} mm")
    st.markdown(
        f'<div class="s-topp"><div class="s-sti">{_under}</div>'
        f'<div class="s-tittel">{_tittel}</div></div>',
        unsafe_allow_html=True,
    )
    if modul not in PROSJEKT_MODULER:
        _areal = float(pd.to_numeric(result["df_kapp"].Areal_m2, errors="coerce").sum())
        _sam = result["sam"]
        kpi_rad([
            kpi("Gulvareal", tall(result["ov"]["A"], 1), "m²"),
            kpi("Panelareal", tall(_areal, 1), "m²"),
            kpi("Elementer", tall(_sam["tot_panel"] + _sam["tak"] + _sam["gulv"]), "stk"),
            kpi("Panelvekt ca.", tall(_areal * estimated_panel_weight(panel_key)), "kg"),
            kpi("Totalpris eks. mva",
                tall(result["tot_pris"]), "kr", "gul"),
        ])

with innhold:
    # ══ MODULER ═══════════════════════════════════════════════════════════════════
    if modul == "Oversikt":
        pass

    elif modul == "Rom":
        # Kolonnen med tegningen følger med når man blar i inndatapanelet (se CSS).
        with st.container(key="tegning_folger"):
            _plan = tegn_plantegning(inp, result, bakfil, apninger=apninger_list or None)
            st.pyplot(_plan, use_container_width=True)
            plt.close(_plan)
        st.caption("Plantegningen oppdateres mens du endrer målene. Snitt, tak, vegger, produksjonstegninger, "
                   "3D og PDF finner du under «Tegninger».")

    elif modul == "Sammenstilling":
        assembly_ui()

    elif modul == "Kalkulasjon":
        st.subheader("Kalkulasjon")
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
        from materialer import materialliste_med_sum
        material_table = materialliste_med_sum(result["df_mat"])
        material_view = material_table.copy()
        material_view["Mengde"] = material_view["Mengde"].map(
            lambda value: "" if pd.isna(value) else f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ","))
        for column in ("Enhetspris (kr)", "Totalpris (kr)"):
            material_view[column] = material_view[column].map(
                lambda value: "–" if pd.isna(value) else f"{value:,.2f}".replace(",", " ").replace(".", ","))
        material_view.loc[material_view.index[-1], "Enhetspris (kr)"] = ""
        st.dataframe(material_view.style.set_properties(
            subset=pd.IndexSlice[[material_view.index[-1]], :],
            **{"background-color": "#07384c", "color": "white", "font-weight": "bold"}),
            use_container_width=True, hide_index=True)
        from cutlist_pdf import cutting_pdf
        st.download_button(
            "Last ned materialliste PDF",
            cutting_pdf([current_room], "kalkulasjon"),
            f"{navn or 'prosjekt'}_materialliste.pdf", "application/pdf",
            key="calculation_material_pdf",
        )
        with st.expander("U-verdi og varmetap"):
            thermal_ui(current_room, st.session_state["project_rooms"])

    elif modul == "FDV":
        st.subheader("FDV")
        st.markdown(lag_fdv_tekst(navn, panel_key, rom_type))
        st.subheader("FDV-oversikt")
        st.dataframe(fdv_df, use_container_width=True, hide_index=True)
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

    elif modul == "Tegninger":
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
        st.subheader("Elementer")
        sam = result["sam"]
        c1, c2, c3 = st.columns(3)
        with c1: st.info(f"Veggelementer: {sam['tot_panel']} stk")
        with c2: st.info(f"Takelementer: {sam['tak']} stk")
        with c3: st.info(f"Gulvelementer: {sam['gulv']} stk" if "Fryserom" in rom_type else "Kjølerom: ingen gulvpanel")
        from purchase_summary import element_cutlist, panel_summary_ui
        cut_export = element_cutlist([current_room])
        st.dataframe(cut_export.round(3), use_container_width=True, hide_index=True)

        panel_summary_ui([current_room])

    if modul in ("Kalkulasjon", "Elementer", "Sammenstilling"):
        finishing_ui(st.session_state["project_rooms"] if modul == "Sammenstilling" else [current_room])
    from cutlist_pdf import pdf_downloads, material_downloads
    if modul in ("Elementer", "Sammenstilling"):
        export_rooms = st.session_state["project_rooms"] if modul == "Sammenstilling" else [current_room]
        if modul == "Sammenstilling" and export_rooms:
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
with lagre_plass:
    project_download(current_room)

st.session_state["_forrige_modul"] = modul

# Første gang oversikten vises finnes ikke utkastet ennå; tegn siden på nytt med rommet.
if (modul == "Oversikt" and oversikt_viste_utkast is False
        and not st.session_state.get("active_room_id") and st.session_state.get("last_valid_editor")):
    st.rerun()
