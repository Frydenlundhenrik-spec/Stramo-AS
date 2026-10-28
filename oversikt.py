"""Prosjektoversikt: romkort, prosjekttotaler og snarveier til leveransene."""
from __future__ import annotations

import html
import json

import pandas as pd
import streamlit as st

from kalkulasjon import beregn_prosjekt
from project_file import world_input

DOKUMENTER = [
    ("Tegninger", ":material/architecture:", "Plan, snitt, tak, vegger, produksjon og 3D"),
    ("Kalkulasjon", ":material/calculate:", "Materialliste og priser"),
    ("Elementer", ":material/view_column:", "Elementlister og kapplister"),
    ("FDV", ":material/description:", "FDV-dokumentasjon"),
    ("Transport", ":material/local_shipping:", "Pakking og transport"),
    ("Sammenstilling", ":material/join_inner:", "Plassering, fellesvegger og IFC"),
]


def tall(verdi: float, desimaler: int = 0) -> str:
    return f"{verdi:,.{desimaler}f}".replace(",", " ").replace(".", ",")


@st.cache_data(show_spinner=False, max_entries=64)
def _rom_tall(rom_json: str) -> dict:
    room = json.loads(rom_json)
    result = beregn_prosjekt(world_input(room), pris_override=room["prices"])
    cuts = result["df_kapp"]
    sam = result["sam"]
    return dict(
        gulvareal=result["ov"]["A"],
        panelareal=float(pd.to_numeric(cuts.Areal_m2, errors="coerce").sum()),
        elementer=int(sam["tot_panel"] + sam["tak"] + sam["gulv"]),
        pris=result["tot_pris"],
    )


def rom_tall(room: dict) -> dict:
    return _rom_tall(json.dumps(room, sort_keys=True, default=str))


def rom_svg(pts, bredde: int = 230, hoyde: int = 120) -> str:
    """Liten omrisstegning av rommet."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs) or 1, max(ys) - min(ys) or 1
    skala = min((bredde - 20) / w, (hoyde - 20) / h)
    ox = (bredde - w * skala) / 2
    oy = (hoyde - h * skala) / 2
    punkter = " ".join(f"{ox + (x - min(xs)) * skala:.1f},{hoyde - oy - (y - min(ys)) * skala:.1f}"
                       for x, y in pts)
    return (f'<svg width="{bredde}" height="{hoyde}" viewBox="0 0 {bredde} {hoyde}">'
            f'<polygon points="{punkter}" fill="#e8f0f5" stroke="#0d3b54" stroke-width="2"/></svg>')


def _rom_info(room: dict) -> str:
    data, form = room["input"], room["form"]
    xs = [p[0] for p in data["pts"]]
    ys = [p[1] for p in data["pts"]]
    if "length_mm" in form:
        mal = f"{tall(form['length_mm'])} × {tall(form['width_mm'])}"
    else:
        mal = f"ca. {tall((max(xs) - min(xs)) * 1000)} × {tall((max(ys) - min(ys)) * 1000)}"
    return f"{form.get('kind', 'Rom')} · {mal} · H {tall(data['hoyde_m'] * 1000)} · {data['panel_key']}"


def _gaa_til(modul: str) -> None:
    st.session_state["ed_module"] = modul


def _apne_rom(room_id: str) -> None:
    from project_ui import open_room
    open_room(room_id)
    st.session_state["ed_module"] = "Rom"


def _nytt_rom(kind: str) -> None:
    from project_ui import start_new_room
    start_new_room(kind)
    st.session_state["ed_module"] = "Rom"


def _nytt_prosjekt() -> None:
    """Slett alle rom, priser og prosjektdata og start på en blank oversikt."""
    revisjon = st.session_state.get("background_revision", 0) + 1
    for key in list(st.session_state):
        del st.session_state[key]
    # Ny revisjon gir et tomt opplastingsfelt for bakgrunnsbilde.
    st.session_state["background_revision"] = revisjon
    st.session_state["ed_module"] = "Oversikt"
    st.session_state["nytt_prosjekt_startet"] = True


def _nytt_prosjekt_knapp() -> None:
    if st.session_state.pop("nytt_prosjekt_startet", False):
        st.toast("Nytt prosjekt startet. Tidligere rom og priser er slettet.", icon=":material/check_circle:")
    with st.popover("Nytt prosjekt", icon=":material/restart_alt:", use_container_width=True):
        st.markdown("**Starte et nytt prosjekt?**")
        st.caption("Alle rom, mål, dører, priser og prosjektinformasjon slettes. Dette kan ikke angres. "
                   "Last ned prosjektfilen i menyen til venstre først hvis du vil ta vare på prosjektet.")
        st.button("Slett og start nytt prosjekt", key="ov_new_project", type="primary",
                  icon=":material/delete:", on_click=_nytt_prosjekt, use_container_width=True)


def kpi(etikett: str, verdi: str, enhet: str = "", ekstra: str = "") -> str:
    enhet_html = f" <small>{enhet}</small>" if enhet else ""
    return (f'<div class="s-kpi {ekstra}"><div class="s-kpi-etikett">{etikett}</div>'
            f'<div class="s-kpi-verdi">{verdi}{enhet_html}</div></div>')


def kpi_rad(kort: list[str]) -> None:
    st.markdown(f'<div class="s-kpi-rad" style="--n:{len(kort)}">{"".join(kort)}</div>',
                unsafe_allow_html=True)


def oversikt_ui() -> bool:
    """Tegner prosjektoversikten. Returnerer True hvis utkastet ble vist."""
    rooms = list(st.session_state.get("project_rooms", []))
    active = st.session_state.get("active_room_id")
    draft = st.session_state.get("last_valid_editor")
    vis_utkast = bool(draft) and not active
    alle = rooms + ([draft] if vis_utkast else [])

    stats = [rom_tall(r) for r in alle]
    kpi_rad([
        kpi("Rom", str(len(rooms)), "", "") if not vis_utkast else
        kpi("Rom", str(len(rooms)), f"+ 1 utkast"),
        kpi("Panelareal totalt", tall(sum(s["panelareal"] for s in stats), 1), "m²"),
        kpi("Elementer", tall(sum(s["elementer"] for s in stats)), "stk"),
        kpi("Totalpris eks. mva",
            tall(sum(s["pris"] for s in stats)), "kr", "gul"),
    ])

    tittel, knapp = st.columns([4, 1], vertical_alignment="bottom")
    tittel.markdown('<div class="s-seksjon-tittel">Rom i prosjektet</div>', unsafe_allow_html=True)
    with knapp:
        _nytt_prosjekt_knapp()
    kort = [(r, s) for r, s in zip(alle, stats)]
    kolonner = st.columns(3, gap="medium")
    for i, (room, s) in enumerate(kort):
        er_utkast = vis_utkast and room is draft
        if er_utkast:
            merke = '<span class="s-merke bla">Utkast – ikke lagt til</span>'
        elif room["id"] == active:
            merke = '<span class="s-merke ok">Åpen</span>'
        else:
            merke = '<span class="s-merke ok">Klar</span>'
        navn = html.escape(room["input"]["navn"] or room["input"]["rom_type"])
        nr = "" if er_utkast else f"{rooms.index(room) + 1}. "
        with kolonner[i % 3]:
            with st.container(border=True, key=f"romkort_{room['id']}"):
                st.markdown(
                    f'<div class="s-romkort-bilde">{rom_svg(room["input"]["pts"])}</div>'
                    f'<div class="s-romkort-tittel"><b>{nr}{navn}</b>{merke}</div>'
                    f'<div class="s-romkort-info">{html.escape(room["input"]["rom_type"])} · {html.escape(_rom_info(room))}</div>'
                    f'<div class="s-romkort-tall"><span><b>{tall(s["panelareal"], 1)}</b> m²</span>'
                    f'<span><b>{s["elementer"]}</b> elementer</span>'
                    f'<span><b>{tall(s["pris"])}</b> kr</span></div>',
                    unsafe_allow_html=True,
                )
                if er_utkast:
                    st.button("Fortsett å tegne", key="ov_open_draft", icon=":material/edit:",
                              on_click=_gaa_til, args=("Rom",), use_container_width=True)
                else:
                    st.button("Åpne rom", key=f"ov_open_{room['id']}", icon=":material/edit:",
                              on_click=_apne_rom, args=(room["id"],), use_container_width=True)
    with kolonner[len(kort) % 3]:
        with st.container(border=True, key="romkort_nytt"):
            st.markdown('<div class="s-nytt-rom">＋<br><span>Nytt rom</span></div>', unsafe_allow_html=True)
            full = len(rooms) >= 30
            st.button("Nytt kjølerom", key="ov_new_cool", on_click=_nytt_rom, args=("Kjølerom",),
                      disabled=full, use_container_width=True)
            st.button("Nytt fryserom", key="ov_new_freezer", on_click=_nytt_rom, args=("Fryserom",),
                      disabled=full, use_container_width=True)

    st.markdown('<div class="s-seksjon-tittel">Dokumenter og leveranse</div>', unsafe_allow_html=True)
    dok_kolonner = st.columns(len(DOKUMENTER), gap="small")
    for kolonne, (modul, ikon, tekst) in zip(dok_kolonner, DOKUMENTER):
        with kolonne:
            st.button(modul, key=f"ov_doc_{modul}",
                      icon=ikon, help=tekst, on_click=_gaa_til, args=(modul,), use_container_width=True)
    return vis_utkast
