from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
from projects import lagre_prosjekt
from branding import LOGO_PATH, logo_finnes, logo_data_uri

st.set_page_config(
    page_title="Stramo kjøleromssystem",
    page_icon=str(LOGO_PATH) if logo_finnes() else "❄️",
    layout="wide",
)

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


def _scroll_til_topp() -> None:
    """
    Tvinger visningen til toppen av siden.

    Chat-feltet nederst får autofokus når det monteres, og nettleseren
    scroller det inn i bildet. Det skjer ved første lasting og hver gang
    modul byttes – da bygges hovedinnholdet på nytt.
    """
    import time
    components.html(
        f"""
        <script>
          // {time.time()} – gjør innholdet unikt slik at skriptet kjører på nytt
          const topp = () => {{
            const d = window.parent.document;
            window.parent.scrollTo(0, 0);
            d.querySelectorAll(
              '[data-testid="stMain"], [data-testid="stAppViewContainer"], section.main'
            ).forEach(el => el.scrollTop = 0);
          }};
          topp();
          requestAnimationFrame(topp);
          [50, 150, 400].forEach(ms => setTimeout(topp, ms));
        </script>
        """,
        height=0,
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
    if logo_finnes():
        st.image(str(LOGO_PATH), width=170)
    else:
        st.title("❄️ Stramo")
    st.caption("Kalkulasjon · FDV · Montasje · Kappliste · IFC")

    modul = st.radio(
        "Velg modul",
        ["Kalkulasjon", "FDV", "Montasjetegninger", "Kapplister"],
    )

    # Ved første lasting og ved modulbytte skal visningen starte på toppen.
    _start_paa_topp = st.session_state.get("_forrige_modul") != modul

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
    breeam_mult=1.0,
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
    f"{rom_type} · Panel: {result['panel']['label']} · Elementbredde: {pw_mm} mm"
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
        st.info("Vegger viser panelfordeling og dørplassering på én vegg.")
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
        # Kameraretningen justeres direkte i 3D-visningen (dra med musen),
        # så egne rotasjon/høydevinkel-slidere er ikke nødvendig.
        fig3 = tegn_3d_modell(inp, apninger=apninger_list or None)
        st.plotly_chart(fig3, use_container_width=True)
        html_str = fig3.to_html(include_plotlyjs="cdn")
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

# Kjøres helt til slutt, etter at chat-feltet har rukket å ta fokus.
# Flagget kvitteres først her, slik at en avbrutt kjøring (st.stop) prøver på nytt.
if _start_paa_topp:
    _scroll_til_topp()
st.session_state["_forrige_modul"] = modul
