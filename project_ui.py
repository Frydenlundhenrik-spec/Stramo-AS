"""Room editing, final assembly and portable project files."""
import base64
import copy
from dataclasses import asdict
import io
import re
import uuid
import zipfile
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import streamlit as st
from database import PANEL_DB
from geometry import wall_lengths
from kalkulasjon import beregn_prosjekt
from montasje import tegn_3d_modell, figur_som_pdf
from ifc_export import gen_ifc
from project_file import (make_room, encode_project, decode_project, validate_room,
                          world_input, snap_room, freezer_shared_walls)


def _editor_key(key):
    return (key.startswith("ed_") or key.startswith("l_side_") or key.startswith("door_price_")
            or key.startswith("ap_") or key in ("l_turns","l_mirrored","last_valid_l_polygon","n_apninger","pris_override")
            or re.fullmatch(r"(?:dt_.+_|da|dw|do|dh|px|py)\d+",key))


def restore_editor(room):
    for key in list(st.session_state):
        if _editor_key(str(key)):
            del st.session_state[key]
    st.session_state["background_revision"] = st.session_state.get("background_revision",0)+1
    st.session_state["editor_background"] = None
    if room is None:
        st.session_state.pop("last_valid_editor", None)
        st.session_state["active_room_id"] = None
        st.session_state["draft_id"] = uuid.uuid4().hex
        return
    data, form = room["input"], room["form"]
    from thermal import thermal_settings
    thermal = thermal_settings(room)
    st.session_state["ed_thermal_room_type"] = data["rom_type"]
    for key, value in thermal.items():
        st.session_state[f"ed_thermal_{key}"] = (value if isinstance(value, bool) else
                                                0.0 if value is None else float(value))
    for key in ("fugemasse", "skum", "pakninger", "alarm"):
        value = form.get("accessory_quantities", {}).get(key) or 0
        st.session_state[f"ed_accessory_{key}"] = float(value) if key == "pakninger" else int(value)
    state = dict(ed_drawing_walls=list(room["excluded_walls"]),ed_panel_stock=form.get("panel_stock_mm",0),ed_finer_width=form.get("plywood_width_mm",1500),ed_finer_length=form.get("plywood_length_mm",3000),ed_name=data["navn"],ed_pnr=data["pnr"],ed_tnr=data["tnr"],
                 ed_date=data["dato"],ed_scale=data["maalestokk"],ed_room_type=data["rom_type"],
                 ed_panel=data["panel_key"],ed_shape=form["kind"],ed_height=round(data["hoyde_m"]*1000),
                 ed_panel_width=round(data["panelbredde_m"]*1000),ed_doors=len(data["dorer"]),
                 ed_beslag=data["beslag_valg"],n_apninger=len(data.get("apninger") or []),
                 pris_override=copy.deepcopy(room["prices"]))
    if form["kind"] == "L-form":
        state.update({f"l_side_{i}":v for i,v in enumerate(form["sides_mm"])})
        state.update(l_turns=form["turns"],l_mirrored=form["mirrored"])
    elif form["kind"] == "Egendefinert polygon":
        state["ed_corners"] = len(form["points_mm"])
        for i,(x,y) in enumerate(form["points_mm"]):
            state[f"px{i}"],state[f"py{i}"] = float(x),float(y)
    else:
        state.update(ed_length=form["length_mm"],ed_width=form["width_mm"])
        if "cut_x_mm" in form:
            state.update(ed_cut_x=form["cut_x_mm"],ed_cut_y=form["cut_y_mm"])
    for i,(key,count,wall,offset,hinge) in enumerate(data["dorer"]):
        state.update({f"dt_{data['rom_type']}_{i}":key,f"da{i}":count,f"dw{i}":wall+1,
                      f"do{i}":round(offset*1000),f"dh{i}":hinge})
    for i,(wall,offset,width,height,sill,label) in enumerate(data.get("apninger") or []):
        state.update({f"ap_w{i}":wall+1,f"ap_off{i}":round(offset*1000),f"ap_bw{i}":round(width*1000),
                      f"ap_bh{i}":round(height*1000),f"ap_sill{i}":round(sill*1000),f"ap_lbl{i}":label})
    for key,value in state.items():
        st.session_state[key] = value
    st.session_state["editor_background"] = room.get("background")
    st.session_state["draft_id"] = room["id"]
    st.session_state["last_valid_editor"] = copy.deepcopy(room)


def prepare_project():
    if "pending_editor" in st.session_state:
        pending = st.session_state.pop("pending_editor")
        restore_editor(pending)
        st.session_state["active_room_id"] = pending["id"] if pending else None
    if "pending_position" in st.session_state:
        rid,position = st.session_state.pop("pending_position")
        st.session_state[f"pos_{rid}_x"],st.session_state[f"pos_{rid}_y"] = position
    for rid in st.session_state.pop("pending_wall_controls",[]):
        st.session_state.pop(f"omit_{rid}",None)
    st.session_state.setdefault("project_rooms",[])


def upload_project():
    with st.expander("Åpne prosjektfil"):
        uploaded = st.file_uploader("Prosjektfil (.json)",type=["json"],key="project_upload")
        if st.button("Åpne prosjekt",disabled=uploaded is None,key="open_project"):
            try:
                project = decode_project(uploaded.getvalue())
            except (ValueError,RecursionError) as exc:
                st.error(f"Kunne ikke åpne prosjektet: {exc}")
            else:
                # Decode and validate everything before replacing live state.
                restore_editor(project["draft"])
                st.session_state["project_rooms"] = project["rooms"]
                st.session_state["active_room_id"] = project.get("active_id")
                for key in list(st.session_state):
                    if str(key).startswith(("pos_","omit_","snap_")) or key == "saved_room_choice":
                        del st.session_state[key]
                st.success("Prosjektet er åpnet. Du kan fortsette å redigere og laste ned en ny prosjektfil.")


def capture_room(inp, form, uploaded_background):
    background = st.session_state.get("editor_background")
    if uploaded_background is not None:
        background = dict(name=uploaded_background.name,
                          data=base64.b64encode(uploaded_background.getvalue()).decode("ascii"))
    room = make_room(inp,form,st.session_state.get("pris_override",{}),background)
    room["id"] = st.session_state.setdefault("draft_id",uuid.uuid4().hex)
    active = st.session_state.get("active_room_id")
    if not active:
        room["excluded_walls"] = [i for i in st.session_state.get("ed_drawing_walls",[]) if i < len(inp.pts)]
    rooms = st.session_state["project_rooms"]
    for i,saved in enumerate(rooms):
        if saved["id"] == active:
            room["id"] = active
            room["position_mm"] = saved["position_mm"]
            if len(saved["input"]["pts"]) == len(inp.pts):
                room["excluded_walls"] = saved["excluded_walls"]
            elif saved["excluded_walls"]:
                st.warning("Antall vegger er endret. Velg utelatte vegger på nytt i sammenstillingen.")
                st.session_state.pop(f"omit_{active}",None)
            break
    # Validate before replacing either the saved room or the recovery snapshot.
    validate_room(room)
    for i, saved in enumerate(rooms):
        if saved["id"] == active:
            rooms[i] = copy.deepcopy(room)
            break
    st.session_state["last_valid_editor"] = copy.deepcopy(room)
    return room


def start_new_room(kind):
    rooms = st.session_state["project_rooms"]
    current = st.session_state.get("last_valid_editor")
    project_fields = {key: st.session_state[key] for key in ("ed_pnr", "ed_date", "ed_scale")
                      if key in st.session_state}
    project_fields["pris_override"] = copy.deepcopy(st.session_state.get("pris_override", {}))
    if current and not st.session_state.get("active_room_id"):
        current = copy.deepcopy(current)
        try:
            validate_room(current)
        except ValueError as exc:
            st.error(f"Rommet kunne ikke lagres: {exc}")
            return
        if rooms:
            right = max(max(p[0] for p in world_input(r).pts) for r in rooms)
            current["position_mm"] = [round((right+1)*1000),0]
        rooms.append(current)
    restore_editor(None)
    st.session_state.update(project_fields)
    names = {r["input"]["navn"] for r in rooms}
    n = 1
    while f"{kind} {n}" in names:
        n += 1
    st.session_state.update(ed_room_type=kind, ed_name=f"{kind} {n}", ed_doors=0,
                            ed_panel="PIR 80 mm" if kind == "Kjølerom" else "PIR 100 mm")


def new_room_controls():
    rooms = st.session_state["project_rooms"]
    st.caption(f"{len(rooms)} rom lagt til i prosjektet.")
    if rooms:
        with st.expander("Hent frem et rom som er lagt til"):
            labels = {r["id"]:f"{i+1}. {r['input']['navn'] or r['input']['rom_type']}" for i,r in enumerate(rooms)}
            selected = st.selectbox("Lagrede rom",list(labels),format_func=labels.get,key="recover_room_choice")
            if st.button("Hent frem rom",key="recover_room"):
                st.session_state["pending_editor"] = copy.deepcopy(next(r for r in rooms if r["id"]==selected))
                st.rerun()
    st.caption("Start et nytt rom her. Tidligere rom beholdes med sist gyldige mål. Nye rom starter uten dører og åpninger.")
    left,right = st.columns(2)
    full = len(st.session_state["project_rooms"]) >= 30
    left.button("Nytt kjølerom", key="new_cool_room", on_click=start_new_room,args=("Kjølerom",),disabled=full)
    right.button("Nytt fryserom", key="new_freezer_room", on_click=start_new_room,args=("Fryserom",),disabled=full)


def room_controls(current):
    rooms = st.session_state["project_rooms"]
    with st.sidebar:
        st.divider()
        st.subheader("Rom i prosjektet")
        active = st.session_state.get("active_room_id")
        if active:
            st.caption("Dette rommet er lagt til. Endringer oppdaterer rommet i prosjektet automatisk.")
        elif st.button("Legg til ferdig rom",key="add_finished_room",disabled=len(rooms)>=30):
            try:
                validate_room(current)
            except ValueError as exc:
                st.error(str(exc))
            else:
                if rooms:
                    right = max(max(p[0] for p in world_input(r).pts) for r in rooms)
                    current["position_mm"] = [round((right+1)*1000),0]
                rooms.append(copy.deepcopy(current))
                st.session_state["active_room_id"] = current["id"]
                st.rerun()
        if active:
            st.button("Tegn nytt rom",key="new_project_room",on_click=start_new_room,args=("Kjølerom",),disabled=len(rooms)>=30)
        if rooms:
            labels = {r["id"]:f"{i+1}. {r['input']['navn'] or r['input']['rom_type']}" for i,r in enumerate(rooms)}
            selected = st.selectbox("Rediger lagret rom",list(labels),format_func=labels.get,key="saved_room_choice")
            if st.button("Åpne rom for redigering",key="edit_project_room"):
                st.session_state["pending_editor"] = copy.deepcopy(next(r for r in rooms if r["id"]==selected))
                st.rerun()
            st.caption("Når rommene er tegnet: velg «Rom og sammenstilling» for plassering og veggvalg.")


def project_download(current):
    rooms = st.session_state["project_rooms"]
    current = next((r for r in rooms if r["id"] == st.session_state.get("active_room_id")), current)
    with st.sidebar:
        st.divider()
        try:
            data = encode_project(rooms, current, st.session_state.get("active_room_id"))
        except ValueError as exc:
            st.error(f"Prosjektet kan ikke lagres før feilen er rettet: {exc}")
            return
        st.download_button("Last ned prosjektfil",data,"stramo-prosjekt.json","application/json",
                            key="download_project",on_click="ignore")
        st.caption("Lagrer rom, mål, rotasjon, dører, priser, bakgrunnsbilde og veggvalg. Inkluderer også rommet du redigerer.")


def finishing_ui(rooms):
    from geometry import beslag_beregning
    from finishing import plywood_cuts, plywood_plan, trim_order, grouped_trim_bars
    from construction import floor_depth
    if st.button("Beregn beslag og gulvplate-kappliste",key="calculate_finishing"):
        st.session_state["show_finishing"] = True
    if not st.session_state.get("show_finishing"):
        return
    st.subheader("Beslag og gulvfiberplater")
    trim_rows, board_rows = [], []
    trim_totals, board_totals = [], []
    for room in rooms:
        inp = world_input(room)
        bb = beslag_beregning(inp.pts,inp.hoyde_m,inp.excluded_walls,PANEL_DB[inp.panel_key]["t"]/1000,inp.hoyde_m-floor_depth(inp.rom_type), floor_angles=inp.rom_type=="Fryserom")
        name = inp.navn or inp.rom_type
        st.write(f"{name}: innvendig 50×50: {bb['stk_inn']} stenger; utvendig 50×150: {bb['stk_ut']} stenger. Alle stenger er 2500 mm, inkludert 10 % svinn/kapp og avrunding opp.")
        for label,key in (("Innvendig 50×50","kapp_inn"),("Utvendig 50×150","kapp_ut")):
            trim_rows.extend(dict(Rom=name,Profil=label,**r) for r in bb[key])
            import math
            waste = 10
            net = sum(2500-r["Rest_mm"] for r in bb[key])/1000
            order = trim_order(net)
            trim_totals.append(dict(Rom=name,Profil=label,Stang="SUM",Deler_stk=sum(r["Kapp"].count(" mm (") for r in bb[key]),
                Løpemeter=net,Kapp_prosent=waste,Lm_med_kapp=net*(1+waste/100),Bestill_stk=order,Bestill_lm=order*2.5))
        if inp.rom_type == "Fryserom":
            form = room["form"]
            w,l = form.get("plywood_width_mm",1500),form.get("plywood_length_mm",3000)
            cuts = plywood_cuts(inp.pts,w,l)
            import math
            waste = 0
            order = len(cuts)
            board_totals.append(dict(Rom=name,Plate="SUM",Deler_stk=len(cuts),Areal_m2=sum(c["Areal_m2"] for c in cuts),
                Kapp_prosent=waste,Bestill_stk=order,Bestill_m2=order*w*l/1000000))
            st.write(f"{name}: {len(cuts)} gulvfiberplater à {w} × {l} × 12 mm. Innenfor veggene, monteres etter veggene.")
            fig = plywood_plan(inp.pts,w,l)
            for cut in cuts:
                board_rows.append(dict(Rom=name,**{k:v for k,v in cut.items() if k!="polygon"}))
            st.pyplot(fig)
            st.download_button('Last ned gulvplateplan PDF', figur_som_pdf(fig,'Gulvplateplan'),
                               f'{name}-gulvplateplan.pdf','application/pdf',key=f'floor_plan_{room["id"]}')
            plt.close(fig)
    st.caption("Beslag: vegghjørner og takkant på begge sider; utelatte vegger tas ut. Kappforslag uten skjøteoverlapp/kuttap. Gulvfiberplater: én råplate per del, uten prosentvis kapptillegg eller gjenbruk av avkapp. Kontroller skjøter og monteringskrav før bestilling.")
    for title,rows,filename in (("Gulvplater",board_rows,"gulvplater-kapp.csv"),):
        if rows:
            frame = pd.DataFrame(grouped_trim_bars(rows) if title=="Beslag" else rows)
            from purchase_summary import with_totals
            summaries = pd.DataFrame(trim_totals if title=="Beslag" else board_totals)
            cols = ["Deler_stk","Løpemeter","Lm_med_kapp","Bestill_stk","Bestill_lm"] if title=="Beslag" else ["Deler_stk","Areal_m2","Bestill_stk","Bestill_m2"]
            summaries = with_totals(summaries,cols,"Rom","SUM ALLE")
            st.dataframe(frame,hide_index=True)
            st.dataframe(summaries.round(3),hide_index=True)
            export = pd.concat([frame,summaries],ignore_index=True)
            st.download_button(f"Last ned {title.lower()}-kappliste",export.to_csv(index=False).encode("utf-8-sig"),filename,"text/csv")


def assembly_plan(rooms):
    from geometry import polygon_winding
    from database import DOR_DB
    from matplotlib.path import Path as PolygonPath
    from matplotlib.patches import Arc
    from drawing_2d import _dim_along_wall, _dh, _dv
    from construction import wall_polygon
    import textwrap
    fig,ax = plt.subplots(figsize=(13,9))
    all_points = []
    inputs = [world_input(room) for room in rooms]
    room_paths = [PolygonPath(np.asarray(inp.pts)) for inp in inputs]
    door_bounds = []
    for inp in inputs:
        points = np.asarray(inp.pts)
        winding = polygon_winding(points)
        for key,count,wall,offset,*hinge_side in inp.dorer:
            if wall in inp.excluded_walls:
                continue
            direction = points[(wall+1)%len(points)]-points[wall]
            direction /= np.linalg.norm(direction)
            width = DOR_DB[key]["bw"]/1000
            outward = winding*np.array([direction[1],-direction[0]])
            right = bool(hinge_side and hinge_side[0] == "Høyre")
            for index in range(count):
                start = points[wall]+direction*(offset+index*(width+.2))
                hinge = start+direction*width if right else start
                closed_direction = -direction if right else direction
                angles = np.linspace(0,np.pi/2,17)
                swing = hinge+width*(np.cos(angles)[:,None]*closed_direction+np.sin(angles)[:,None]*outward)
                envelope = np.vstack([swing,hinge])
                door_bounds.append((envelope.min(axis=0)-.12,envelope.max(axis=0)+.12))
    for ri,inp in enumerate(inputs):
        pts = np.array(inp.pts)
        all_points.extend(np.vstack([wall_polygon(pts,i,PANEL_DB[inp.panel_key]['t']/1000,inp.excluded_walls)
                         for i in range(len(pts)) if i not in inp.excluded_walls]))
        winding = polygon_winding(pts)
        color = "#74b8cf" if inp.rom_type=="Fryserom" else "#e9c96e"
        ax.fill(pts[:,0],pts[:,1],color=color,alpha=.2)
        # Choose an interior location with clearance from every wall, also in an L-room.
        gx, gy = np.meshgrid(np.linspace(pts[:,0].min(), pts[:,0].max(), 31),
                             np.linspace(pts[:,1].min(), pts[:,1].max(), 31))
        candidates = np.column_stack([gx.ravel(), gy.ravel()])
        candidates = candidates[PolygonPath(pts).contains_points(candidates, radius=-.01)]
        clearance = np.full(len(candidates), np.inf)
        for a, b in zip(pts, np.roll(pts, -1, axis=0)):
            edge = b - a
            t = np.clip((candidates - a) @ edge / (edge @ edge), 0, 1)
            clearance = np.minimum(clearance, np.linalg.norm(candidates - a - t[:,None]*edge, axis=1))
        label_at = candidates[np.argmax(clearance)] if len(candidates) else pts.mean(axis=0)
        ax.text(*label_at, textwrap.fill(inp.navn or inp.rom_type, width=24),
                ha="center",va="center",fontsize=10,color="#07384c",bbox=dict(fc="white",ec="none",alpha=.85))
        for i,a in enumerate(pts):
            b = pts[(i+1)%len(pts)]
            omitted = i in inp.excluded_walls
            if not omitted:
                wall = wall_polygon(pts, i, PANEL_DB[inp.panel_key]["t"]/1000,
                                          excluded_walls=inp.excluded_walls)
                if wall is not None:
                    ax.fill(wall[:,0],wall[:,1],color="#183b50")
            ax.plot([a[0],b[0]],[a[1],b[1]],color="#a0a0a0" if omitted else "#183b50",
                    lw=1 if omitted else 3,linestyle="--" if omitted else "-")
            mid = (a+b)/2
            ax.annotate(f"V{i+1}",mid,xytext=(4,4),
                        textcoords="offset points",fontsize=7,color="#555")
            if not omitted:
                outward = winding*np.array([(b-a)[1], -(b-a)[0]])/np.linalg.norm(b-a)
                door_widths = [DOR_DB[d[0]]["bw"]/1000 for d in inp.dorer if d[1] > 0 and d[2] == i]
                lane = max(.48, max(door_widths, default=0)+.30)
                dimension_at = mid+outward*lane
                if not any(path.contains_point(dimension_at) for j,path in enumerate(room_paths) if j != ri):
                    for _ in range(16):
                        endpoints = np.array([a,b])+outward*lane
                        low, high = endpoints.min(axis=0), endpoints.max(axis=0)
                        if not any(np.all(high >= door_low) and np.all(low <= door_high) for door_low,door_high in door_bounds):
                            break
                        lane += .25
                    _dim_along_wall(ax, a, b, f"{np.linalg.norm(b-a)*1000:.0f} mm innv.", offset=lane,
                                    fs=9, col="#07384c", winding=winding, total=True)
        for key,count,wall,offset,*hinge_side in inp.dorer:
            if wall in inp.excluded_walls:
                continue
            width = DOR_DB[key]["bw"]/1000
            a,b = pts[wall],pts[(wall+1)%len(pts)]
            direction = (b-a)/np.linalg.norm(b-a)
            for k in range(count):
                start = a+direction*(offset+k*(width+.2))
                end = start+direction*width
                outward=winding*np.array([direction[1],-direction[0]])
                edge=outward*PANEL_DB[inp.panel_key]['t']/1000
                opening=np.array([start,end,end+edge,start+edge])
                ax.fill(opening[:,0],opening[:,1],color='white',zorder=5)
                ax.plot([start[0],end[0]],[start[1],end[1]],color="white",lw=5,zorder=6)
                ax.plot([start[0],end[0]],[start[1],end[1]],color="#b53737",lw=1.5,zorder=7)
                outward = winding * np.array([direction[1], -direction[0]])
                right = bool(hinge_side and hinge_side[0] == "Høyre")
                hinge = end if right else start
                angle = np.degrees(np.arctan2(direction[1], direction[0])) + (180 if right else 0)
                t1, t2 = (0, 90) if right else (-90, 0)
                if winding < 0:
                    t1, t2 = -t2, -t1
                leaf = hinge + outward * width
                ax.add_patch(Arc(hinge, width*2, width*2, angle=angle, theta1=t1, theta2=t2,
                                 color="#315b7d", lw=1))
                ax.plot([hinge[0],leaf[0]],[hinge[1],leaf[1]],color="#315b7d",lw=1)
    if len(rooms) > 1 and all_points:
        xy = np.asarray(all_points)
        low, high = xy.min(axis=0), xy.max(axis=0)
        outer_lane = max([DOR_DB[d[0]]["bw"]/1000 for inp in inputs for d in inp.dorer if d[1] > 0]+[.9])+1.30
        _dh(ax, low[0], high[0], low[1], f"{(high[0]-low[0])*1000:.0f} mm utvendig",
            ey=low[1]-outer_lane, fs=11, col="#07384c", total=True)
        _dv(ax, low[1], high[1], high[0], f"{(high[1]-low[1])*1000:.0f} mm utvendig",
            ex=high[0]+outer_lane, fs=11, col="#07384c", total=True)
    ax.set_aspect("equal"); ax.margins(.14)
    ax.set_title("Plantegning", fontweight="bold", color="#07384c")
    ax.axis("off")
    fig.tight_layout()
    return fig


def assembly_ui():
    st.header("Rom og sammenstilling")
    rooms = st.session_state["project_rooms"]
    if not rooms:
        st.info("Tegn et rom og trykk «Legg til ferdig rom». Gjenta for neste rom, og sett dem sammen her til slutt.")
        return
    st.caption("Plasser ferdigtegnede rom. Velg deretter vegger som skal utelates. Rommenes grunntegning beholdes og kan redigeres senere.")
    labels = {r["id"]:f"{i+1}. {r['input']['navn'] or r['input']['rom_type']}" for i,r in enumerate(rooms)}
    for room in rooms:
        rid = room["id"]
        with st.expander(labels[rid],expanded=True):
            c1,c2 = st.columns(2)
            x = c1.number_input("X-plassering (mm)",value=float(room["position_mm"][0]),min_value=-1000000.,max_value=1000000.,step=100.,key=f"pos_{rid}_x")
            y = c2.number_input("Y-plassering (mm)",value=float(room["position_mm"][1]),min_value=-1000000.,max_value=1000000.,step=100.,key=f"pos_{rid}_y")
            room["position_mm"] = [x,y]
            lengths = wall_lengths(room["input"]["pts"])
            st.caption("Avsluttende veggvalg: slå av veggen her, ikke slett hjørnepunktene.")
            room["excluded_walls"] = st.multiselect("Vegger som skal utelates",list(range(len(lengths))),
                default=room["excluded_walls"],format_func=lambda i, lengths=tuple(lengths):f"V{i+1} – {lengths[i]*1000:.0f} mm",key=f"omit_{rid}")
            if room["excluded_walls"]:
                st.caption("Veggen, tilhørende U-kanal og dører/åpninger utelates fra sammenstillingen, mengdene og IFC. Du kan slå veggen på igjen.")
    st.subheader("Koble rom mot en vegg")
    if len(rooms)>1:
        moving_id = st.selectbox("Rom som skal flyttes",list(labels),format_func=labels.get,key="snap_moving")
        target_id = st.selectbox("Rom som skal beholdes på plass",[rid for rid in labels if rid!=moving_id],format_func=labels.get,key="snap_target")
        moving = next(r for r in rooms if r["id"]==moving_id)
        target = next(r for r in rooms if r["id"]==target_id)
        own_wall = st.selectbox("Vegg på rommet som flyttes",range(len(moving["input"]["pts"])),format_func=lambda i:f"V{i+1}",key="snap_own_wall")
        target_wall = st.selectbox("Vegg det skal kobles mot",range(len(target["input"]["pts"])),format_func=lambda i:f"V{i+1}",key="snap_target_wall")
        st.caption("Kobler mot utsiden av veggen som beholdes, med plass til paneltykkelsen. Veggene må vende mot hverandre.")
        if st.button("Plasser inntil valgt vegg",key="snap_apply"):
            try:
                if target_wall in target["excluded_walls"]:
                    raise ValueError("Velg en vegg som beholdes.")
                position = snap_room(moving,own_wall,target,target_wall)
            except ValueError as exc:
                st.error(str(exc))
            else:
                moving["position_mm"] = position
                st.session_state["pending_position"] = (moving_id,position)
                st.rerun()
    matches = freezer_shared_walls(rooms)
    if matches:
        st.info("Fant kjøleromsvegger som er helt dekket av fryseromsvegger. Fryseromsveggene beholdes.")
        for cool,wall,freezer,fw in matches:
            st.write(f"{labels[cool]} V{wall+1} → bruker {labels[freezer]} V{fw+1}")
        if st.button("Bruk fryseromsvegger som fellesvegger",key="apply_shared_walls"):
            affected = []
            for cool,wall,_,_ in matches:
                room = next(r for r in rooms if r["id"]==cool)
                room["excluded_walls"] = sorted(set(room["excluded_walls"]+[wall]))
                affected.append(cool)
            st.session_state["pending_wall_controls"] = affected
            st.rerun()
    fig = assembly_plan(rooms)
    st.pyplot(fig)
    pdf = figur_som_pdf(fig)
    plt.close(fig)
    st.download_button("Last ned sammenstilling PDF",pdf,"sammenstilling.pdf","application/pdf")
    show_roof = st.checkbox("Vis gjennomsiktig tak i samlet 3D",value=True,key="assembly_roof_transparent")
    combined = go.Figure()
    materials, cuts = [],[]
    for ri,room in enumerate(rooms):
        inp = world_input(room)
        result = beregn_prosjekt(inp,pris_override=room["prices"])
        for source,target in ((result["df_mat"],materials),(result["df_kapp"],cuts)):
            frame = source.copy()
            frame.insert(0,"Rom",labels[room["id"]])
            target.append(frame)
        figure = tegn_3d_modell(inp,apninger=inp.apninger)
        for trace in figure.data:
            if not show_roof and (re.match(r"T\d",trace.name or "") or (trace.name or "").startswith(("Omriss T", "Takskravering"))):
                continue
            trace.name = labels[room["id"]]+" · "+str(trace.name)
            trace.legendgroup = room["id"]
            combined.add_trace(trace)
    if st.button("Rett opp / nullstill 3D",key="reset_assembly_camera"):
        st.session_state["assembly_camera_revision"] = st.session_state.get("assembly_camera_revision",0)+1
    combined.update_layout(scene=dict(aspectmode="data",xaxis_title="X (m)",yaxis_title="Y (m)",zaxis_title="Z (m)",
        dragmode="turntable",camera=dict(eye=dict(x=1.6,y=-1.7,z=1.15),up=dict(x=0,y=0,z=1),projection=dict(type="orthographic"))),
        legend=dict(orientation="h",yanchor="top",y=-.03,xanchor="left",x=0),
        margin=dict(l=0,r=0,t=15,b=110),
        uirevision=st.session_state.get("assembly_camera_revision",0),height=760)
    st.plotly_chart(combined,use_container_width=True,config=dict(modeBarButtonsToRemove=["orbitRotation"]))
    mat, cut = pd.concat(materials,ignore_index=True),pd.concat(cuts,ignore_index=True)
    from purchase_summary import element_cutlist, panel_summary_ui
    cut = element_cutlist(rooms)
    st.dataframe(cut,hide_index=True)
    panel_summary_ui(rooms)
    st.download_button("Last ned samlet kappliste",cut.to_csv(index=False).encode("utf-8-sig"),"kappliste.csv","text/csv")
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for i,room in enumerate(rooms):
            inp = world_input(room)
            archive.writestr(f"rom-{i+1}.ifc",gen_ifc(inp.pts,inp.hoyde_m,inp.navn,inp.panel_key,
                inp.dorer,inp.rom_type,inp.panelbredde_m,apninger=inp.apninger,excluded_walls=inp.excluded_walls))
    st.download_button("Last ned IFC-filer per rom (ZIP)",bundle.getvalue(),"rom-ifc.zip","application/zip")
    st.caption("IFC-filene har samme koordinatsystem og inneholder veggene som er valgt i sammenstillingen.")

