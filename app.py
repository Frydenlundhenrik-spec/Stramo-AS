from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from database import PANEL_DB, BESLAG_DB, DOR_DB, FORM_MALER, PANELER, load_databases
from geometry import wall_lengths, validate_polygon
from kalkulasjon import ProjectInput, beregn_prosjekt, kalkulasjon_sammendrag
from fdv import lag_fdv_oversikt, lag_fdv_tekst
from montasje import (
    tegn_plantegning, tegn_snitt, tegn_3d_modell,
    tegn_taktegning, tegn_veggoppstaltt, tegn_produksjonsfigurer,
    figur_som_png, figur_som_pdf, figurer_som_samlet_pdf, lag_tegningsinfo,
)
from ifc_export import gen_ifc
from export_excel import lag_excel
from export_pdf import lag_enkel_pdf, lag_tilbuds_pdf
from chatbot import vis_chatbot
from projects import (
    lagre_prosjekt, hent_alle_prosjekter, hent_prosjekt,
    slett_prosjekt, oppdater_prosjekt,
)

st.set_page_config(page_title="Stramo kjøleromssystem", page_icon="❄️", layout="wide")

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
    dorer_mat = [(d[0], d[1]) for d in dorer_tuple]
    inp = ProjectInput(
        navn, pnr, tnr, dato, maalestokk, rom_type, panel_key,
        list(pts_tuple), H, pw_m, dorer_mat, list(beslag_tuple),
        apninger=list(apninger_tuple),
    )
    return beregn_prosjekt(inp, pris_override=pris_override, breeam_multiplier=breeam_mult)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("❄️ Stramo")
    st.caption("Kalkulasjon · FDV · Montasje · Kappliste · IFC")

    modul = st.radio(
        "Velg modul",
        ["Kalkulasjon", "FDV", "Montasjetegninger",
         "Kapplister", "IFC-eksport", "Samlet eksport", "Prisredigering"],
    )

    # ── Prosjekthåndtering ────────────────────────────────────────────────────
    st.divider()
    with st.expander("💾 Prosjekthåndtering", expanded=False):
        prosjekter = hent_alle_prosjekter()
        if prosjekter:
            proj_labels = {p["id"]: f"{p['navn']}  ({p['dato']})" for p in prosjekter}
            valgt_id = st.selectbox(
                "Last inn prosjekt",
                [None] + list(proj_labels.keys()),
                format_func=lambda x: "– velg –" if x is None else proj_labels[x],
            )
            if valgt_id and st.button("📂 Last inn"):
                data = hent_prosjekt(valgt_id)
                if data:
                    for k, v in data.items():
                        st.session_state[k] = v
                    st.success("Prosjekt lastet inn!")
                    st.rerun()
            if valgt_id and st.button("🗑️ Slett", type="secondary"):
                slett_prosjekt(valgt_id)
                st.success("Slettet.")
                st.rerun()
        else:
            st.info("Ingen lagrede prosjekter.")

    # ── Prosjektinfo ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📋 Prosjektinfo")
    navn        = st.text_input("Prosjektnavn", st.session_state.get("navn", ""),
                                 placeholder="Skriv inn prosjektnavn...")
    pnr         = st.text_input("Prosjektnr", st.session_state.get("pnr", "1001"))
    tnr         = st.text_input("Tegningsnr", st.session_state.get("tnr", "A101"))
    dato        = st.text_input("Dato", st.session_state.get("dato", datetime.today().strftime("%d.%m.%Y")))
    maalestokk  = st.text_input("Målestokk", st.session_state.get("maalestokk", "1:10"))

    if st.button("💾 Lagre prosjekt"):
        save_data = dict(
            navn=navn, pnr=pnr, tnr=tnr, dato=dato, maalestokk=maalestokk,
        )
        lagre_prosjekt(navn or "Uten navn", save_data)
        st.success("Lagret!")

    # ── Romtype og panel ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("🌡️ Romtype og panel")
    rom_type = st.radio("Romtype", ["Kjølerom", "Fryserom"])

    # Alle paneltyper kan velges fritt
    _panel_keys = list(PANELER.keys())
    _panel_labels = {k: f"{PANELER[k].navn}  (U={PANELER[k].u_verdi} W/m²K)" for k in _panel_keys}
    default_panel = "PIR 80 mm" if rom_type == "Kjølerom" else "PIR 100 mm"
    default_idx   = _panel_keys.index(default_panel)
    panel_key = st.selectbox(
        "Paneltype",
        _panel_keys,
        index=default_idx,
        format_func=lambda k: _panel_labels[k],
    )
    pan_info = PANELER[panel_key]
    st.info(
        f"U-verdi: {pan_info.u_verdi} W/m²K  ·  "
        f"CO₂: {pan_info.co2_kg_m2} kg/m²  ·  "
        f"Pris: {pan_info.pris_nok_m2} kr/m²"
    )

    # ── Romform ───────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🏠 Romform")
    form_valg = st.selectbox("Form", list(FORM_MALER.keys()))
    st.caption(FORM_MALER[form_valg]["besk"])
    H_mm = st.number_input("Romhøyde (mm)", min_value=1800, max_value=8000, value=2500, step=50)
    H = H_mm / 1000.0

    if form_valg != "Egendefinert polygon":
        c1, c2 = st.columns(2)
        with c1:
            L_mm = st.number_input("Lengde (mm)", min_value=500, max_value=50000, value=5850, step=50)
        with c2:
            B_mm = st.number_input("Bredde (mm)", min_value=500, max_value=30000, value=4450, step=50)
        L_inp = L_mm / 1000.0
        B_inp = B_mm / 1000.0
        if form_valg == "Femkant – avskåret hjørne":
            cc1, cc2 = st.columns(2)
            with cc1:
                CX_mm = st.number_input("Avskjær X (mm)", min_value=50, max_value=L_mm, value=1100, step=50)
            with cc2:
                CY_mm = st.number_input("Avskjær Y (mm)", min_value=50, max_value=B_mm, value=1100, step=50)
            CX = CX_mm / 1000.0
            CY = CY_mm / 1000.0
        else:
            CX = CY = 0.0
        pts = FORM_MALER[form_valg]["func"](L_inp, B_inp, CX, CY)
    else:
        n_pts = int(st.number_input("Antall hjørner", min_value=3, max_value=16, value=5, step=1))
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

    # Polygon-validering
    poly_ok = True
    try:
        validate_polygon(pts)
    except ValueError as e:
        st.error(f"⚠️ Ugyldig polygon: {e}")
        poly_ok = False

    # ── Elementbredde ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📏 Elementbredde")
    pw_mm = st.number_input("Elementbredde (mm)", min_value=300, max_value=2000, value=1100, step=50)
    pw_m  = pw_mm / 1000.0

    # ── Dører med veggplassering ──────────────────────────────────────────────
    st.divider()
    st.subheader("🚪 Dører")
    nd_t = int(st.number_input("Antall dørtyper", min_value=0, max_value=4, value=1, step=1))

    dorer_full = []   # (dk, ant, wall_idx, offset_m)  for tegninger
    dorer_mat  = []   # (dk, ant)                       for materialer/kalkulasjon
    wls_count  = len(pts)

    for i in range(nd_t):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            dk = st.selectbox(f"Type {i+1}", list(DOR_DB.keys()),
                              format_func=lambda k: DOR_DB[k]["label"], key=f"dt{i}")
        with c2:
            da = st.number_input("Stk", min_value=0, max_value=10, value=1, key=f"da{i}")
        with c3:
            wall_idx = st.number_input(
                "Vegg nr", min_value=1, max_value=wls_count, value=1, step=1, key=f"dw{i}"
            ) - 1
        h1, h2 = st.columns(2)
        with h1:
            offset_mm = st.number_input(
                f"Offset fra hjørne (mm) – type {i+1}", min_value=100, max_value=10000,
                value=350, step=50, key=f"do{i}"
            )
        with h2:
            hengsel = st.selectbox(
                "Hengslingsside", ["Venstre", "Høyre"], key=f"dh{i}",
                help="Siden hengslet sitter på (sett innenfra rommet)"
            )
        offset_m = offset_mm / 1000.0
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
        default=list(BESLAG_DB.keys())[:5],
        format_func=lambda k: BESLAG_DB[k]["label"],
    )

    # ── BREEAM-lite ───────────────────────────────────────────────────────────
    st.divider()
    with st.expander("🌱 Miljøkrav (BREEAM-inspirert)", expanded=False):
        st.caption("Legger til miljøkostnad som prispavikling – etter prinsipp fra NS-EN 15978.")
        breeam_level = st.selectbox("Miljønivå", list(BREEAM_MULTIPLIERS.keys()), index=0)
        breeam_mult  = BREEAM_MULTIPLIERS[breeam_level]
        if breeam_level != "Ingen":
            st.info(
                f"Prisjustering: +{round((breeam_mult-1)*100)}%  ·  "
                f"Faktor: {breeam_mult:.2f}  ·  "
                "Inkluderer miljøoppfølging, avfallshåndtering og lavkarbonmaterialer."
            )

    st.divider()
    bakfil = st.file_uploader("Bakgrunn plantegning PNG/JPG", type=["png","jpg","jpeg"])

    # ── Prisredigering (session state) ────────────────────────────────────────
    if "pris_override" not in st.session_state:
        st.session_state["pris_override"] = {}

# ── Beregning (caches dersom input ikke er endret) ────────────────────────────
import json as _json

if not poly_ok:
    st.error("Rett polygon-feilen i sidebar for å fortsette.")
    st.stop()

_cache_key = dict(
    panel_key=panel_key, rom_type=rom_type,
    pts_tuple=tuple(tuple(p) for p in pts),
    H=H, pw_m=pw_m,
    dorer_tuple=tuple((d[0], d[1]) for d in dorer_mat),
    beslag_tuple=tuple(beslag_valg),
    navn=navn, pnr=pnr, tnr=tnr, dato=dato, maalestokk=maalestokk,
    pris_json=_json.dumps(st.session_state["pris_override"], sort_keys=True),
    breeam_mult=breeam_mult,
    apninger_tuple=tuple(tuple(a) for a in apninger_list) if apninger_list else (),
)
result   = _beregn_cached(**_cache_key)
fdv_df   = lag_fdv_oversikt(panel_key, rom_type, dorer_mat, beslag_valg)

# ProjectInput med full dorer_full (for tegninger)
inp = ProjectInput(
    navn, pnr, tnr, dato, maalestokk, rom_type, panel_key,
    pts, H, pw_m, dorer_full, beslag_valg,
    apninger=apninger_list if apninger_list else [],
)

# ── Hoved-header ──────────────────────────────────────────────────────────────
st.title(f"❄️ {navn.strip() or 'Kjølerom'}")
st.caption(
    f"{rom_type} · Panel: {result['panel']['label']} · "
    f"Elementbredde: {pw_mm} mm"
    + (f"  ·  BREEAM {breeam_level}" if breeam_level != "Ingen" else "")
)

k1, k2, k3, k4, k5 = st.columns(5)
with k1: card("Gulvareal",   f"{result['ov']['A']} m²")
with k2: card("Volum",       f"{result['ov']['V']} m³")
with k3: card("Omkrets",     f"{result['ov']['P']} m")
with k4: card("Kostnad",     f"{result['tot_pris']:,.0f} kr".replace(",", " "))
with k5: card("CO₂",        f"{result['tot_co2']:,.0f} kg".replace(",", " "))

st.divider()

# ══ MODULER ═══════════════════════════════════════════════════════════════════

if modul == "Kalkulasjon":
    st.header("📦 Kalkulasjon")
    st.subheader("Sammendrag")
    st.dataframe(kalkulasjon_sammendrag(result), use_container_width=True, hide_index=True)
    st.subheader("Materialliste")
    st.dataframe(result["df_mat"], use_container_width=True, hide_index=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Totalpris", f"{result['tot_pris']:,.0f} kr".replace(",", " "))
    with c2:
        st.metric("CO₂", f"{result['tot_co2']:,.0f} kg".replace(",", " "))
    with c3:
        kr_m2 = result["tot_pris"] / result["ov"]["A"] if result["ov"]["A"] else 0
        st.metric("Kr/m²", f"{kr_m2:,.0f} kr".replace(",", " "))
    if breeam_level != "Ingen":
        st.info(
            f"💡 Prisene inkluderer BREEAM {breeam_level}-tillegg "
            f"(+{round((breeam_mult-1)*100)}%)."
        )
    st.download_button(
        "Last ned materialliste CSV",
        result["df_mat"].to_csv(index=False).encode("utf-8-sig"),
        f"{navn or 'prosjekt'}_materialliste.csv", "text/csv",
    )

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
        pdf = lag_enkel_pdf(f"FDV – {navn or 'Kjølerom'}",
                            lag_fdv_tekst(navn, panel_key, rom_type).splitlines())
        st.download_button(
            "Last ned FDV PDF", pdf,
            f"{navn or 'prosjekt'}_fdv.pdf", "application/pdf",
        )
    except Exception as exc:
        st.info(str(exc))

elif modul == "Montasjetegninger":
    st.header("📐 Montasjetegninger")
    tab_plan, tab_snitt, tab_tak, tab_oppsalt, tab_prod, tab_3d = st.tabs(
        ["Plantegning", "Snitt", "Taktegning", "Veggoppstalt", "Produksjonstegninger", "3D"]
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
        vdf = pd.DataFrame([{
            "Vegg": f"V{i+1}", "Lengde (m)": round(w, 3),
            "Lengde (mm)": round(w*1000),
            "Antall elementer": math.ceil(w/pw_m),
        } for i, w in enumerate(wall_lengths(pts))])
        st.dataframe(vdf, use_container_width=True, hide_index=True)

    with tab_snitt:
        wls = wall_lengths(pts)
        vegg_options = [f"Vegg {i+1}  ({wls[i]*1000:.0f} mm)" for i in range(len(wls))]
        valgt  = st.selectbox("Velg snitt-vegg", vegg_options)
        v_idx  = vegg_options.index(valgt)
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
        st.info("Veggoppstalt viser panelfordeling og dørplassering på én vegg.")
        wls2 = wall_lengths(pts)
        v_opts2 = [f"Vegg {i+1}  ({wls2[i]*1000:.0f} mm)" for i in range(len(wls2))]
        valgt2 = st.selectbox("Velg vegg", v_opts2, key="oppstalt_vegg")
        v_idx2 = v_opts2.index(valgt2)
        fig2 = tegn_veggoppstaltt(inp, result, v_idx2, apninger=apninger_list or None)
        st.pyplot(fig2, use_container_width=True)
        pdf2 = figur_som_pdf(fig2)
        plt.close(fig2)
        st.download_button(
            "Last ned veggoppstalt PDF", pdf2,
            f"{tnr}_{navn or 'prosjekt'}_vegg{v_idx2+1}.pdf", "application/pdf",
        )

    with tab_prod:
        st.info(
            "Produksjonstegninger viser hvert element med nøyaktige mål, vinkler og "
            "snittbeskrivelse – klart for verkstedproduksjon og modulmontering på byggeplass. "
            "**F** = Fabrikkant (ingen kapping)  ·  **RK** = Rett kapp (90°)  ·  "
            "**VK** = Vinklet kapp (se snittvinkel i tabell per element)."
        )
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
        c1, c2 = st.columns([1, 4])
        with c1:
            azimuth   = st.slider("Rotasjon",     -180, 180,  -55, 5)
            elevation = st.slider("Høydevinkel",     5,  85,   28, 5)
        with c2:
            fig3 = tegn_3d_modell(inp, azimuth, elevation, apninger=apninger_list or None)
            st.plotly_chart(fig3, use_container_width=True)
            html = fig3.to_html(include_plotlyjs="cdn").encode("utf-8")
            st.download_button(
                "Last ned interaktiv 3D HTML", html,
                f"{tnr}_{navn or 'prosjekt'}_3d.html", "text/html",
            )
            ifc_3d = gen_ifc(
                pts, H, navn or "Kjolerom", panel_key,
                dorer_full, rom_type, pw_m,
                apninger=apninger_list if apninger_list else None,
            )
            st.download_button(
                "Last ned IFC", ifc_3d,
                f"{tnr}_{navn or 'prosjekt'}.ifc", "application/octet-stream",
                key="dl_ifc_3d",
            )

elif modul == "Kapplister":
    st.header("🔪 Kapplister")
    sam = result["sam"]
    c1, c2, c3 = st.columns(3)
    with c1: st.info(f"Veggelementer: {sam['tot_panel']} stk")
    with c2: st.info(f"Takelementer: {sam['tak']} stk")
    with c3: st.info(f"Gulvelementer: {sam['gulv']} stk" if "Fryserom" in rom_type else "Kjølerom: ingen gulvpanel")
    st.caption("Taklogikk: elementer har samme bredde som veggelementer og går vegg-til-vegg.")
    st.dataframe(result["df_kapp"], use_container_width=True, hide_index=True)
    st.download_button(
        "Last ned kappliste CSV",
        result["df_kapp"].to_csv(index=False).encode("utf-8-sig"),
        f"{navn or 'prosjekt'}_kappliste.csv", "text/csv",
    )

elif modul == "IFC-eksport":
    st.header("🏗️ IFC-eksport")
    st.info(
        "IFC2X3 med vegger (booleanske åpninger for dører og klassfronter), "
        "gulv, takpaneler og gulvpaneler (fryserom). "
        "Åpnes i Solibri, BIM 360, Revit m.fl."
    )
    ifc = gen_ifc(
        pts, H, navn or "Kjolerom", panel_key,
        dorer_full, rom_type, pw_m,
        apninger=apninger_list if apninger_list else None,
    )
    st.success(f"IFC klar: {len(ifc)//1024} kB")
    st.download_button(
        "Last ned IFC", ifc,
        f"{tnr}_{navn or 'prosjekt'}.ifc", "application/octet-stream",
    )

elif modul == "Samlet eksport":
    st.header("📥 Samlet eksport")

    # Full tilbuds-PDF med tegninger
    st.subheader("Full tilbuds-PDF (inkl. tegninger)")
    with st.spinner("Genererer plantegning og snitt…"):
        _fig_plan  = tegn_plantegning(inp, result, bakfil, apninger=apninger_list or None)
        _png_plan  = figur_som_png(_fig_plan).read()
        plt.close(_fig_plan)
        _fig_snitt = tegn_snitt(inp, result, 0, "A-A", apninger=apninger_list or None)
        _png_snitt = figur_som_png(_fig_snitt).read()
        plt.close(_fig_snitt)
    try:
        pi = dict(
            navn=navn or "–", pnr=pnr, tnr=tnr, dato=dato,
            rom_type=rom_type, panel_label=result["panel"]["label"],
        )
        tilbuds = lag_tilbuds_pdf(pi, result, result["df_mat"], _png_plan, _png_snitt)
        st.download_button(
            "📄 Last ned full tilbuds-PDF", tilbuds,
            f"{navn or 'prosjekt'}_tilbud.pdf", "application/pdf",
        )
    except Exception as e:
        st.warning(f"PDF-generering feilet: {e}. Installer: pip install reportlab")

    st.subheader("Andre formater")
    excel = lag_excel(result, fdv_df)
    st.download_button("Last ned samlet Excel", excel,
        f"{navn or 'prosjekt'}_samlet.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("Materialliste CSV",
        result["df_mat"].to_csv(index=False).encode("utf-8-sig"),
        f"{navn or 'prosjekt'}_materialliste.csv", "text/csv")
    st.download_button("Kappliste CSV",
        result["df_kapp"].to_csv(index=False).encode("utf-8-sig"),
        f"{navn or 'prosjekt'}_kappliste.csv", "text/csv")
    st.download_button("FDV CSV",
        fdv_df.to_csv(index=False).encode("utf-8-sig"),
        f"{navn or 'prosjekt'}_fdv.csv", "text/csv")
    ifc = gen_ifc(pts, H, navn or "Kjolerom", panel_key, dorer_mat, rom_type, pw_m)
    st.download_button("IFC", ifc, f"{tnr}_{navn or 'prosjekt'}.ifc", "application/octet-stream")

elif modul == "Prisredigering":
    st.header("🏷️ Prisredigering")
    st.info(
        "Her kan du justere priser for denne sesjonen. "
        "Prisene lagres ikke permanent – bruk 'Lagre prosjekt' for å bevare dem."
    )
    override = dict(st.session_state.get("pris_override", {}))
    pan = PANEL_DB[panel_key]

    st.subheader("Panelpris")
    new_pan = st.number_input(
        f"Vegg/tak panel – {pan['label']} (kr/m²)",
        min_value=100, max_value=10000,
        value=int(override.get("vegg_0", pan["pris"])), step=10,
    )
    for i in range(len(wall_lengths(pts))):
        override[f"vegg_{i}"] = float(new_pan)
    override["tak"] = float(new_pan)

    st.subheader("Gulvpriser")
    if rom_type.startswith("Kjølerom"):
        st.caption("Kjølerom: gulvet er eksisterende betong – ikke inkludert i kalkulasjon.")
    else:
        new_pir = st.number_input(
            "PIR gulvpanel (kr/m²)", min_value=100, max_value=5000,
            value=int(override.get("gulv_pir", 650)), step=10,
        )
        new_spon = st.number_input(
            "Sponplate m/ plastbelegg (kr/m²)", min_value=50, max_value=2000,
            value=int(override.get("gulv_spon", 330)), step=10,
        )
        override["gulv_pir"]  = float(new_pir)
        override["gulv_spon"] = float(new_spon)

    st.subheader("U-kanal og beslag")
    override["ukan"] = float(st.number_input(
        "U-kanal 80 mm (kr/stk à 3 m)", min_value=50, max_value=2000,
        value=int(override.get("ukan", 220)), step=10,
    ))
    override["beslag_inn"] = float(st.number_input(
        "Innv. hjørnebeslag 50×50 mm (kr/stk à 2,5 m)", min_value=50, max_value=2000,
        value=int(override.get("beslag_inn", 185)), step=10,
    ))
    override["beslag_ut"] = float(st.number_input(
        "Utv. hjørnebeslag 50×125 mm (kr/stk à 2,5 m)", min_value=50, max_value=2000,
        value=int(override.get("beslag_ut", 265)), step=10,
    ))

    st.subheader("Dørpriser")
    for dk in DOR_DB:
        d = DOR_DB[dk]
        override[f"dor_{dk}"] = float(st.number_input(
            f"{d['label']} (kr/stk)", min_value=1000, max_value=200000,
            value=int(override.get(f"dor_{dk}", d["pris"])), step=500,
        ))

    if st.button("✅ Bruk disse prisene"):
        st.session_state["pris_override"] = override
        st.success("Prisene er oppdatert – kalkulasjonen vil bruke disse verdiene.")
    if st.button("🔄 Tilbakestill til standardpriser"):
        st.session_state["pris_override"] = {}
        st.success("Tilbakestilt til standardpriser.")

    with st.expander("Vis gjeldende prisoverride"):
        st.json(st.session_state.get("pris_override", {}))

# ── AI-assistent (vises alltid nederst, utenfor modul-blokken) ────────────────
ov = result.get("ov", {})
_kontekst = f"""
Prosjekt: {navn or '(ikke navngitt)'}
Rom-type: {rom_type}
Panel: {PANEL_DB[panel_key]['label']} ({PANEL_DB[panel_key]['t']} mm)
Panelbredde: {round(pw_m*1000)} mm
Areal: {ov.get('A', '–')} m²
Omkrets: {ov.get('P', '–')} m
Romhøyde: {H*1000:.0f} mm
Antall vegger: {len(pts)}
Estimert totalkostnad: {result.get('total_eks_mva', '–')} kr eks. mva
"""
vis_chatbot(kontekst=_kontekst)

st.markdown("---")
st.caption("Stramo kjøleromssystem · kalkulasjon, FDV, montasje, kapplister og IFC")
