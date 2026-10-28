"""Order summaries share the full-blank quantities used by the calculation."""
import pandas as pd
from kalkulasjon import beregn_prosjekt
from project_file import world_input
from database import PANEL_DB
from kappliste import panel_order_rows

BALEX_WEIGHTS = {"PIR 80 mm":11.8, "PIR 100 mm":12.6, "PIR 120 mm":13.2}


def estimated_panel_weight(panel_key):
    # Balex PIR STANDARD product sheet, 22.10.2026, page 3.
    # Other selectable products retain an explicitly labelled approximation.
    return BALEX_WEIGHTS.get(panel_key, round(8.6 + .04*PANEL_DB[panel_key]["t"],2))


def panel_summary(rooms):
    rows = []
    for room in rooms:
        inp = world_input(room)
        weight = estimated_panel_weight(inp.panel_key)
        documented = inp.panel_key in BALEX_WEIGHTS
        cut = beregn_prosjekt(inp)["df_kapp"]
        blanks = panel_order_rows(cut, round(inp.hoyde_m*1000), round(inp.panelbredde_m*1000))
        for zone, group in blanks.groupby("Vegg",sort=False):
            for length, part in group.groupby("Leveringslengde_mm", sort=False):
                count = len(part)
                ordered = count
                delivery = int(length)  # Ordered to the room's actual required length.
                fits = delivery >= length
                order_area = float(part.Bestill_m2.sum()) if fits else None
                area = float(part.Areal_m2.sum())
                rows.append(dict(Rom=inp.navn,Del=zone,Panel=inp.panel_key,
                    Deler_stk=int(part.Deler_stk.sum()),Elementer_stk=count,Løpemeter=float(part.Løpemeter.sum()),
                    Areal_m2=area,Kg_pr_m2=weight,Vektgrunnlag="Balex produktdatablad" if documented else "ESTIMAT",
                    Vekt_netto_kg=area*weight,
                    Leveringslengde_mm=delivery,Bredde_mm=round(inp.panelbredde_m*1000),Tykkelse_mm=PANEL_DB[inp.panel_key]["t"],
                    Bestill_hele_elementer=ordered if fits else None,
                    Bestill_lm=ordered*delivery/1000 if fits else None,
                    Bestill_m2=order_area,Bestill_vekt_kg=order_area*weight if fits and weight else None,
                    Merknad="Leveringslengde for kort – ingen skjøting beregnet" if not fits else
                        ("Estimert panelvekt; uten dører, beslag, finer og emballasje" if not documented else "Panelvekt uten tilbehør og emballasje")))
    return pd.DataFrame(rows)


def grouped_panels(rooms):
    frame=panel_summary(rooms)
    if frame.empty:return frame
    keys=["Panel","Leveringslengde_mm","Bredde_mm","Tykkelse_mm"]
    sums=["Bestill_hele_elementer","Bestill_lm","Bestill_m2","Bestill_vekt_kg"]
    return frame.groupby(keys,as_index=False,sort=False).agg(
        **{c:(c,"sum") for c in sums},
        Vektgrunnlag=("Vektgrunnlag",lambda values:", ".join(dict.fromkeys(values))))


def grouped_cuts(rooms):
    rows=[]
    for room in rooms:
        inp=world_input(room)
        f=beregn_prosjekt(inp)["df_kapp"].copy()
        f=f[pd.to_numeric(f.Bredde_mm,errors="coerce").notna()]
        for _, p in f.iterrows():
            role = "V" if p.Vegg.startswith("Vegg") else "T" if p.Vegg == "Tak" else "G"
            standard = (int(p.Bredde_mm) == round(inp.panelbredde_m*1000)
                        and abs(p.Areal_m2-p.Bredde_mm*p.Høyde_mm/1e6)<.002
                        and "Utsparing" not in p.Type)
            thickness = PANEL_DB[inp.panel_key]["t"]
            rows.append(dict(Panel=f"STD {role} {thickness} mm" if standard else f"{p.Elementnavn} {thickness} mm",
                Rom=inp.navn, Referanse=p.Vegg, Høyde_mm=p.Høyde_mm,
                Bredde_mm=p.Bredde_mm, Tykkelse_mm=thickness, Antall_stk=1,
                Areal_m2=p.Areal_m2, Vekt_kg=p.Areal_m2*estimated_panel_weight(inp.panel_key),
                order="VTG".index(role)*2+(not standard)))
    if not rows:return pd.DataFrame()
    frame=pd.DataFrame(rows).sort_values("order",kind="stable")
    keys=["Panel","Høyde_mm","Bredde_mm","Tykkelse_mm"]
    # References remain visible, including the room when IDs repeat between rooms.
    frame["Referanse"] = frame.Rom + " · " + frame.Referanse
    def references(values):
        by_room={}
        for value in values:
            room, zone=value.rsplit(" · ",1)
            by_room.setdefault(room,[])
            if zone not in by_room[room]:by_room[room].append(zone)
        return "; ".join(room+" · "+(
            "Vegg "+", ".join(z.removeprefix("Vegg ") for z in zones)
            if all(z.startswith("Vegg ") for z in zones) else ", ".join(zones))
            for room,zones in by_room.items())
    return frame.groupby(keys,sort=False,as_index=False).agg(
        Referanse=("Referanse",references),
        Antall_stk=("Antall_stk","sum"),Areal_m2=("Areal_m2","sum"),Vekt_kg=("Vekt_kg","sum"))


def element_cutlist(rooms):
    """Element-facing cut list with matching dimensions combined across rooms."""
    frame = with_totals(grouped_cuts(rooms), ["Antall_stk", "Areal_m2", "Vekt_kg"], "Panel")
    return frame.rename(columns={"Høyde_mm":"Høyde / lengde (mm)", "Bredde_mm":"Bredde (mm)",
        "Tykkelse_mm":"Tykkelse (mm)", "Antall_stk":"Antall (stk)",
        "Areal_m2":"Areal (m²)", "Vekt_kg":"Vekt (kg)"})


def with_totals(frame, columns, label_column, label="SUM"):
    if frame.empty:
        return frame
    row = {label_column:label}
    for col in columns:
        values = pd.to_numeric(frame[col],errors="coerce")
        # Do not show a misleading partial total when any weight/order input is missing.
        row[col] = values.sum() if values.notna().all() else None
    return pd.concat([frame,pd.DataFrame([row])],ignore_index=True)


PANEL_TOTAL_COLUMNS = ["Deler_stk","Elementer_stk","Løpemeter","Areal_m2","Vekt_netto_kg",
                       "Bestill_hele_elementer","Bestill_lm","Bestill_m2","Bestill_vekt_kg"]


def cutlist_totals(frame):
    frame = frame.copy()
    panel = pd.to_numeric(frame.Bredde_mm,errors="coerce").notna()
    frame["Løpemeter"] = pd.to_numeric(frame.Høyde_mm,errors="coerce").fillna(0)/1000
    frame["Deler_stk"] = 1
    summaries = []
    for mask,label in ((panel,"SUM PANELELEMENTER"),(~panel,"SUM FINER – AREAL")):
        part = frame[mask]
        if not part.empty:
            summaries.append(dict(Elementnavn=label,Deler_stk=len(part),Løpemeter=part.Løpemeter.sum(),Areal_m2=part.Areal_m2.sum()))
    return pd.concat([frame,pd.DataFrame(summaries)],ignore_index=True)


def panel_summary_ui(rooms):
    import streamlit as st
    st.subheader("Sum og bestilling – panelelementer")
    frame = grouped_panels(rooms).drop(columns="Bestill_lm", errors="ignore")
    total = with_totals(frame,["Bestill_hele_elementer","Bestill_m2","Bestill_vekt_kg"],"Panel").rename(columns={
        "Leveringslengde_mm":"Høyde / lengde (mm)", "Bredde_mm":"Bredde (mm)", "Tykkelse_mm":"Tykkelse (mm)",
        "Bestill_hele_elementer":"Antall (stk)", "Bestill_m2":"Areal (m²)", "Bestill_vekt_kg":"Vekt (kg)"})
    st.dataframe(total.round(3),hide_index=True)
    st.caption("Elementer bestilles på beregnet lengde. Kompatible kapp fordeles på hele råelementer med 3 mm sagspor, uten prosentvis kapptillegg. Kalkulasjon, bestillingsliste og transport bruker samme bestillingsmengder.")
    st.caption("Panelvekt beregnes automatisk som areal × kg/m². Balex PIR STANDARD: 80 mm = 11,8, 100 mm = 12,6 og 120 mm = 13,2 kg/m² (produktdatablad 22.10.2026, side 3). Andre paneltyper merkes ESTIMAT. Tilbehør og emballasje er ikke inkludert.")
    with st.expander("Kappfordeling på hele elementer"):
        plan = panel_cutting_plan(rooms)
        st.dataframe(plan, hide_index=True)
    return total


def panel_cutting_plan(rooms):
    rows=[]
    for room in rooms:
        inp=world_input(room)
        cut=beregn_prosjekt(inp)["df_kapp"]
        blanks=panel_order_rows(cut,round(inp.hoyde_m*1000),round(inp.panelbredde_m*1000))
        for number, blank in enumerate(blanks.itertuples(), 1):
            rows.append(dict(Rom=inp.navn,Råelement=f"R{number}",Panel=inp.panel_key,
                Leveringslengde_mm=blank.Leveringslengde_mm,Bredde_mm=blank.Bredde_mm,
                Elementer=blank.Elementnavn,Kappbredder_mm=" + ".join(map(str,blank.Kappbredder_mm)),
                Sagspor_mm=blank.Sagspor_mm,Restbredde_mm=blank.Restbredde_mm))
    return pd.DataFrame(rows)
