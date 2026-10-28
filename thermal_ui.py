"""Editable operating conditions and transmission heat calculations."""
import pandas as pd
import streamlit as st

from thermal import calculate_project, thermal_settings


def thermal_inputs(room_type, expanded=False):
    defaults = thermal_settings({"input": {"rom_type": room_type}, "form": {}})
    previous_type = st.session_state.get("ed_thermal_room_type", room_type)
    if previous_type != room_type:
        st.session_state["ed_thermal_inside_c"] = defaults["inside_c"]
    st.session_state["ed_thermal_room_type"] = room_type
    for field, value in defaults.items():
        st.session_state.setdefault(f"ed_thermal_{field}", 0.0 if value is None else value)
    values = {}
    with st.expander("Temperatur og U-verdi", expanded=expanded):
        st.caption("Verdiene lagres med rommet i prosjektfilen. +18 °C er valgt som standard rundt rommene.")
        for field, label, low, high in (
            ("inside_c", "Temperatur i rommet (°C)", -60.0, 60.0),
            ("ambient_c", "Temperatur utenfor veggene (°C)", -60.0, 80.0),
            ("ceiling_c", "Temperatur over taket (°C)", -60.0, 80.0),
            ("ground_c", "Temperatur under gulvet (°C)", -40.0, 60.0),
        ):
            values[field] = st.number_input(label, min_value=low, max_value=high,
                                            step=1.0, key=f"ed_thermal_{field}")
        values["rh_pct"] = st.number_input("Relativ luftfuktighet utenfor (%)", min_value=1.0,
                                           max_value=100.0, step=5.0, key="ed_thermal_rh_pct")
        values["conditions_confirmed"] = st.checkbox(
            "Jeg har kontrollert temperaturene og luftfuktigheten for prosjektet",
            key="ed_thermal_conditions_confirmed")
        st.caption("+15 °C under gulvet og 60 % luftfuktighet er foreløpige eksempelverdier. Fellesvegger bruker naborommets temperatur automatisk.")
        if room_type == "Kjølerom" and values["inside_c"] > 4:
            st.caption("Matvarer: +5 °C er en beregningsverdi. Lett bedervelige varer krever normalt +4 °C eller lavere, eller temperaturen angitt på varen.")
        st.caption("U-verdi i W/m²K. La feltet stå på 0 når dokumentasjon mangler. Paneler bruker dokumentert Balex STANDARD-verdi når den finnes.")
        for field, label in (
            ("door_u", "Dokumentert U-verdi for lukkede dører (0 = ukjent)"),
            ("floor_u", "U-verdi for eksisterende kjøleromsgulv (0 = ukjent)"),
            ("panel_u", "Egen dokumentert U-verdi for panel (0 = automatisk)"),
        ):
            value = st.number_input(label, min_value=0.0, max_value=20.0, step=0.01,
                                    format="%.3f", key=f"ed_thermal_{field}",
                                    disabled=field == "floor_u" and room_type == "Fryserom")
            values[field] = value or None
        limit = st.number_input("Valgt grense for varmefluks (W/m², 0 = ingen)",
                                min_value=0.0, max_value=100.0, step=1.0,
                                key="ed_thermal_heat_flux_limit")
        values["heat_flux_limit"] = limit or None
        st.caption("En grense må velges for prosjektet. Det finnes ikke én automatisk godkjent paneltykkelse for alle kjøle- og fryserom.")
    return values


def surface_table(result):
    return pd.DataFrame([{
        "Flate": row["surface"], "Areal (m²)": round(row["area_m2"], 3),
        "U (W/m²K)": row["u"], "Naboside (°C)": row["neighbor_c"],
        "Temperaturforskjell (K)": row["delta_t"],
        "Varme inn (W)": None if row["watts"] is None else round(row["watts"], 1),
        "Merknad": row["note"],
    } for row in result["surfaces"]])


def thermal_ui(current_room, project_rooms):
    st.subheader("U-verdi og varmetap")
    st.write("Beregningen bruker rommets tegnede flater, paneltype og temperatur på hver side. Positiv verdi er varme inn i rommet; negativ verdi er varme fra rommet til en kaldere nabo.")
    rooms = project_rooms if any(r["id"] == current_room["id"] for r in project_rooms) else [current_room]
    choices = [r["id"] for r in rooms]
    labels = {r["id"]: r["input"]["navn"] or r["input"]["rom_type"] for r in rooms}
    if len(rooms) > 1:
        choices.insert(0, "all")
        labels["all"] = "Alle rom i prosjektet"
    if st.session_state.get("thermal_scope") not in choices:
        st.session_state["thermal_scope"] = "all" if len(rooms) > 1 else current_room["id"]
    selected = st.selectbox("Vis beregning for", choices, format_func=labels.get, key="thermal_scope")
    selected_ids = [r["id"] for r in rooms] if selected == "all" else [selected]
    try:
        result = calculate_project(rooms)
    except ValueError as exc:
        st.error(f"Varmeberegningen kan ikke fullføres: {exc}")
        return
    shown = [r for r in result["rooms"] if r["id"] in selected_ids]
    st.info("Dette er en foreløpig transmisjonsberegning, Q = U × A × ΔT. Døråpning, luftlekkasje, varer, personer, lys, vifter og avriming kommer i tillegg ved dimensjonering av kjøleanlegg. Kuldebroer i hjørner og terskler krever egen vurdering.")
    for room_result in shown:
        room = next(r for r in rooms if r["id"] == room_result["id"])
        settings = thermal_settings(room)
        st.subheader(room_result["name"])
        st.caption(f"Inne {settings['inside_c']:g} °C · rundt vegger {settings['ambient_c']:g} °C · over tak {settings['ceiling_c']:g} °C · under gulv {settings['ground_c']:g} °C · RF {settings['rh_pct']:g} %")
        if not settings["conditions_confirmed"]:
            st.warning("Foreløpige driftsforhold: kontroller særlig temperatur under gulvet og luftfuktighet i sidepanelet.")
        cols = st.columns(3)
        cols[0].metric("Beregnet varme inn", f"{room_result['known_positive_w']:.1f} W")
        cols[1].metric("Beregnet varme ut", f"{abs(room_result['known_negative_w']):.1f} W")
        cols[2].metric("Netto transmisjon" if not room_result["unknown_surface_count"] else "Kjent delsum, netto", f"{room_result['known_net_w']:.1f} W")
        if room_result["unknown_surface_count"]:
            st.warning(f"Ufullstendig grunnlag: {room_result['unknown_area_m2']:.2f} m² har ukjent U-verdi eller tilslutning. Disse flatene er ikke regnet som null varmetap.")
        for warning in room_result["warnings"]:
            st.caption(warning)
        st.dataframe(surface_table(room_result), hide_index=True, use_container_width=True)
        st.markdown("**Sammenlign paneltykkelser**")
        rows = []
        for panel in room_result["panel_comparison"]:
            rows.append({"Balex PIR STANDARD": f"PIR {panel['thickness_mm']} mm", "U (W/m²K)": panel["u"],
                         "Største varmefluks i rommets egne paneler (W/m²)": round(panel["max_abs_heat_flux_w_m2"], 2),
                         "Valgt grense": "Ingen grense angitt" if panel["meets_flux_limit"] is None else
                         ("Innenfor valgt grense" if panel["meets_flux_limit"] else "Over valgt grense")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("Sammenligningen gjelder selve panelet. Ingen paneltykkelse endres automatisk. Gulvet i kjølerommet må vurderes ut fra faktisk gulvoppbygging.")
    if len(shown) > 1:
        st.metric("Prosjektets kjente netto transmisjon", f"{sum(r['known_net_w'] for r in shown):.1f} W")
        st.caption("Varmeoverføring gjennom registrerte fellesvegger opptrer med motsatt fortegn i de to rommene og kansellerer i prosjektets netto sum.")
    st.markdown("**Hva kan kreve tykkere panel?** Lavere romtemperatur, høyere temperatur rundt rommet eller et strengere mål for varmefluks gjør lavere U-verdi mer aktuelt. Større areal øker samlet varmebelastning. Fuktighet påvirker kondensrisiko, særlig ved skjøter, hjørner og terskler. U-verdi alene dokumenterer ikke kondenssikkerhet.")
    st.markdown("Kilde: [Balex PIR STANDARD](https://balex.eu/en/products/sandwich-panels/pu-w-st-wall-sandwich-panel-polyurethane-core), produktdatablad s. 3–4 og teknisk katalog s. 26. Uc inkluderer produktets skjøter og innfestingspunkter. [Mattilsynets råd om lagring](https://www.mattilsynet.no/mat-og-drikke/forbrukere/rad-for-oppbevaring-av-mat).")
    from thermal_pdf import thermal_pdf
    st.download_button("Last ned U-verdi og varmetap PDF", thermal_pdf(rooms, selected_ids),
                       "Stramo-U-verdi-og-varmetap.pdf", "application/pdf", key="thermal_pdf_download")
