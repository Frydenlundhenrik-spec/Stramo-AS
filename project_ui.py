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
from branding import project_name
from geometry import wall_lengths, pentagon_sides, polygon_winding
from kalkulasjon import beregn_prosjekt
from montasje import tegn_3d_modell, figur_som_pdf
from ifc_export import gen_ifc
from project_file import (make_room, encode_project, decode_project, validate_room,
                          world_input, snap_room, freezer_shared_walls, placement_points)


def _editor_key(key):
    return (key.startswith("ed_") or key.startswith("l_side_") or key.startswith("door_price_")
            or key.startswith("ap_") or key in ("l_turns","l_mirrored","last_valid_l_polygon","n_apninger","pris_override")
            or re.fullmatch(r"(?:dt_.+_|da|dw|do|dh|px|py)\d+",key))


def restore_editor(room):
    for key in list(st.session_state):
        if _editor_key(str(key)):
            del st.session_state[key]
    # Explicitly synchronize the existing radio widget with the calculation
    # page; deleting its key alone leaves the browser's old selection visible.
    st.session_state["ed_module"] = "Rom"
    st.session_state["background_revision"] = st.session_state.get("background_revision",0)+1
    st.session_state["editor_background"] = None
    if room is None:
        st.session_state.pop("last_valid_editor", None)
        st.session_state["active_room_id"] = None
        st.session_state["draft_id"] = uuid.uuid4().hex
        return
    data = room["input"]
    form = copy.deepcopy(room["form"])
    from construction import floor_outline
    from dimensions import corner_shift
    from project_file import _form_points
    thickness = PANEL_DB[data["panel_key"]]["t"]/1000
    if form.get("dimension_basis") != "external":
        outer = np.asarray(floor_outline(data["pts"], thickness))
        if form["kind"] == "L-form":
            form["sides_mm"] = [round(v*1000) for v in wall_lengths(outer)]
        elif form["kind"] == "Rektangel":
            lengths = wall_lengths(outer)
            form.update(length_mm=round(lengths[0]*1000), width_mm=round(lengths[1]*1000))
        else:
            form.update(kind="Egendefinert polygon", points_mm=(outer*1000).tolist(), turns=0, mirrored=False)
        generated = np.asarray(_form_points(form))
        shift = outer[0]-generated[0]
        if not np.allclose(generated+shift, outer):
            form.update(kind="Egendefinert polygon", points_mm=(outer*1000).tolist(), turns=0, mirrored=False)
            shift = np.zeros(2)
        form.update(dimension_basis="external", origin_mm=(shift*1000).tolist())
    st.session_state["ed_form_origin"] = form.get("origin_mm", [0,0])
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
                 ed_turns=form.get("turns",0),ed_mirrored=form.get("mirrored",False),
                 ed_panel=data["panel_key"],ed_shape=form["kind"],ed_height=round(data["hoyde_m"]*1000),
                 ed_panel_width=round(data["panelbredde_m"]*1000),ed_doors=len(data["dorer"]),
                 ed_beslag=data["beslag_valg"],n_apninger=len(data.get("apninger") or []),
                 pris_override=copy.deepcopy(room["prices"]))
    if form["kind"] == "L-form":
        state.update({f"l_side_{i}":v for i,v in enumerate(form["sides_mm"])})
    elif form["kind"] == "Egendefinert polygon":
        state["ed_corners"] = len(form["points_mm"])
        for i,(x,y) in enumerate(form["points_mm"]):
            state[f"px{i}"],state[f"py{i}"] = float(x),float(y)
    elif form["kind"] == "Femkant – avskåret hjørne":
        sides = pentagon_sides(form["length_mm"], form["width_mm"], form["cut_x_mm"], form["cut_y_mm"])
        state.update({f"ed_pentagon_side_{i}": float(v) for i, v in enumerate(sides)})
    else:
        state.update(ed_length=form["length_mm"],ed_width=form["width_mm"])
    for i,(key,count,wall,offset,hinge) in enumerate(data["dorer"]):
        state.update({f"dt_{data['rom_type']}_{i}":key,f"da{i}":count,f"dw{i}":wall+1,
                      f"do{i}":round((offset+corner_shift(data["pts"], thickness, wall))*1000),f"dh{i}":hinge})
    for i,(wall,offset,width,height,sill,label) in enumerate(data.get("apninger") or []):
        state.update({f"ap_w{i}":wall+1,f"ap_off{i}":round((offset+corner_shift(data["pts"], thickness, wall))*1000),f"ap_bw{i}":round(width*1000),
                      f"ap_bh{i}":round(height*1000),f"ap_sill{i}":round(sill*1000),f"ap_lbl{i}":label})
    for key,value in state.items():
        st.session_state[key] = value
    st.session_state["editor_background"] = room.get("background")
    st.session_state["draft_id"] = room["id"]
    st.session_state["last_valid_editor"] = copy.deepcopy(room)


def prepare_project():
    if "pending_project" in st.session_state:
        _apply_project(st.session_state.pop("pending_project"))
    if "pending_editor" in st.session_state:
        pending = st.session_state.pop("pending_editor")
        restore_editor(pending)
        st.session_state["active_room_id"] = pending["id"] if pending else None
    if "pending_position" in st.session_state:
        rid,position = st.session_state.pop("pending_position")
        st.session_state[f"pos_{rid}_x"],st.session_state[f"pos_{rid}_y"] = position
    for rid in st.session_state.pop("pending_wall_controls",[]):
        room = next((room for room in st.session_state.get("project_rooms", []) if room["id"] == rid), None)
        if room is not None:
            # Set the widget value explicitly: deleting its key can restore the
            # browser's previous selection on the following rerun.
            st.session_state[f"omit_{rid}"] = list(room["excluded_walls"])
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
                # The menu is already drawn above this button, so the project is
                # applied at the start of the next run instead of mid-script.
                st.session_state["pending_project"] = project
                st.rerun()
        if st.session_state.pop("project_opened", False):
            st.success("Prosjektet er åpnet. Du kan fortsette å redigere og laste ned en ny prosjektfil.")


def _apply_project(project):
    # Decode and validate everything before replacing live state.
    restore_editor(project["draft"])
    st.session_state["project_rooms"] = project["rooms"]
    st.session_state["active_room_id"] = project.get("active_id")
    for key in list(st.session_state):
        if str(key).startswith(("pos_","omit_","snap_")) or key in ("saved_room_choice", "room_picker"):
            del st.session_state[key]
    st.session_state["project_opened"] = True


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
                if 'placement' in saved:
                    room['placement'] = copy.deepcopy(saved['placement'])
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


DRAFT_CHOICE = "__utkast__"


def open_room(choice):
    """Åpne et lagret rom i redigeringen. Et utkast som ikke er lagt til, lagres først."""
    rooms = st.session_state["project_rooms"]
    if choice in (None, DRAFT_CHOICE) or choice == st.session_state.get("active_room_id"):
        return
    current = st.session_state.get("last_valid_editor")
    if current and not st.session_state.get("active_room_id") and len(rooms) < 30:
        current = copy.deepcopy(current)
        try:
            validate_room(current)
        except ValueError:
            pass
        else:
            right = max(max(p[0] for p in world_input(r).pts) for r in rooms)
            current["position_mm"] = [round((right+1)*1000),0]
            rooms.append(current)
    st.session_state["pending_editor"] = copy.deepcopy(next(r for r in rooms if r["id"] == choice))


def _switch_room():
    open_room(st.session_state.get("room_picker"))


def room_bar():
    """Romvelger øverst i inndatapanelet: bytt rom og start nytt rom.

    Tegnes før beregningen, slik at man kan bytte rom også når målene er ugyldige."""
    rooms = st.session_state["project_rooms"]
    active = st.session_state.get("active_room_id")
    labels = {r["id"]:f"{i+1}. {project_name(r['input']['navn']) or r['input']['rom_type']}" for i,r in enumerate(rooms)}
    options = list(labels)
    if not active:
        name = (st.session_state.get("ed_name") or "").strip() or st.session_state.get("ed_room_type") or "Nytt rom"
        labels[DRAFT_CHOICE] = f"{name} (ikke lagt til)"
        options.append(DRAFT_CHOICE)
    st.session_state["room_picker"] = active if active in labels else DRAFT_CHOICE
    st.selectbox("Rom", options, format_func=labels.get, key="room_picker", on_change=_switch_room,
                 help="Bytt mellom rommene i prosjektet. Endringer lagres automatisk i rommet.")
    full = len(rooms) >= 30
    left, right = st.columns(2)
    left.button("Kjølerom", key="new_cool_room", icon=":material/add:", on_click=start_new_room,
                args=("Kjølerom",), disabled=full, use_container_width=True,
                help="Start et nytt kjølerom. Rommet du står i beholdes i prosjektet.")
    right.button("Fryserom", key="new_freezer_room", icon=":material/add:", on_click=start_new_room,
                 args=("Fryserom",), disabled=full, use_container_width=True,
                 help="Start et nytt fryserom. Rommet du står i beholdes i prosjektet.")


def add_room_button(current):
    """Legg utkastet til i prosjektet, eller vis at rommet allerede er lagt til."""
    rooms = st.session_state["project_rooms"]
    full = len(rooms) >= 30
    if st.session_state.get("active_room_id"):
        st.caption(":material/check_circle: Rommet er lagt til. Endringer lagres automatisk.")
    elif st.button("Legg til rommet i prosjektet", key="add_finished_room", type="primary",
                   icon=":material/playlist_add:", disabled=full, use_container_width=True):
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


def project_download(current):
    rooms = st.session_state["project_rooms"]
    current = next((r for r in rooms if r["id"] == st.session_state.get("active_room_id")), current)
    try:
        data = encode_project(rooms, current, st.session_state.get("active_room_id"))
    except ValueError as exc:
        st.error(f"Prosjektet kan ikke lagres før feilen er rettet: {exc}")
        return
    st.download_button("Last ned prosjektfil",data,"stramo-prosjekt.json","application/json",
                        key="download_project",on_click="ignore",icon=":material/save:",use_container_width=True,
                        help="Lagrer rom, mål, rotasjon, dører, priser, bakgrunnsbilde og veggvalg. Inkluderer også rommet du redigerer.")


def finishing_ui(rooms):
    from geometry import beslag_beregning
    from finishing import plywood_cuts, plywood_plan, trim_order, grouped_trim_bars, board_count
    from construction import floor_depth
    if st.button("Beregn beslag og gulvplate-kappliste",key="calculate_finishing"):
        st.session_state["show_finishing"] = True
    if not st.session_state.get("show_finishing"):
        return
    st.subheader("Beslag og gulvplater")
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
            order = board_count(cuts)
            board_totals.append(dict(Rom=name,Plate="SUM",Deler_stk=len(cuts),Areal_m2=sum(c["Areal_m2"] for c in cuts),
                Kapp_prosent=waste,Bestill_stk=order,Bestill_m2=order*w*l/1000000))
            st.write(f"{name}: {order} gulvplater à {w} × {l} × 12 mm. Innenfor veggene, monteres etter veggene.")
            fig = plywood_plan(inp.pts,w,l,PANEL_DB[inp.panel_key]['t']/1000)
            for cut in cuts:
                board_rows.append(dict(Rom=name,**{k:v for k,v in cut.items() if k in ("Plate", "Bredde_mm", "Lengde_mm", "Areal_m2", "Råplate")}))
            st.pyplot(fig)
            st.download_button('Last ned gulvplateplan PDF', figur_som_pdf(fig,'Gulvplateplan'),
                               f'{name}-gulvplateplan.pdf','application/pdf',key=f'floor_plan_{room["id"]}')
            plt.close(fig)
    st.caption("Beslag: vegghjørner og takkant på begge sider; utelatte vegger tas ut. Kappforslag uten skjøteoverlapp/kuttap. Gulvplater: avkapp over 200 mm i begge retninger vurderes for gjenbruk, med 3 mm sagspor. Ingen prosentvis kapptillegg. Kontroller skjøter og monteringskrav før bestilling.")
    for title,rows in (("Gulvplater",board_rows),):
        if rows:
            frame = pd.DataFrame(grouped_trim_bars(rows) if title=="Beslag" else rows)
            from purchase_summary import with_totals
            summaries = pd.DataFrame(trim_totals if title=="Beslag" else board_totals)
            cols = ["Deler_stk","Løpemeter","Lm_med_kapp","Bestill_stk","Bestill_lm"] if title=="Beslag" else ["Deler_stk","Areal_m2","Bestill_stk","Bestill_m2"]
            summaries = with_totals(summaries,cols,"Rom","SUM ALLE")
            st.dataframe(frame,hide_index=True)
            st.dataframe(summaries.round(3),hide_index=True)


def _arrange_assembly_labels(ax):
    """Place names and wall labels in free space using their rendered text bounds."""
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    movable = [text for text in ax.texts if hasattr(text, '_plan_candidates')]
    fixed = [text.get_window_extent(renderer).expanded(1.04, 1.12)
             for text in ax.texts if text.get_text() and text not in movable]
    # Room names have first choice; wall labels can slide along their own wall.
    movable.sort(key=lambda text: text.get_gid() != 'room-name')
    for text in movable:
        best, best_score = text.get_position(), float('inf')
        for point in text._plan_candidates:
            text.set_position(point)
            box = text.get_window_extent(renderer).expanded(1.04, 1.12)
            corners = ax.transData.inverted().transform(box.get_points())
            x1,y1 = corners[0]; x2,y2 = corners[1]
            if not text._plan_room.contains_points([[x1,y1],[x1,y2],[x2,y1],[x2,y2]]).all():
                continue
            score = sum(box.overlaps(other) for other in fixed)
            if score < best_score:
                best, best_score = point, score
            if score == 0:
                break
        text.set_position(best)
        fixed.append(text.get_window_extent(renderer).expanded(1.04, 1.12))


def assembly_plan(rooms, highlight=None):
    from drawing_2d import stramo_plan, _tegn_fig_title_block
    from montasje import lag_tegningsinfo
    from construction import floor_outline
    from matplotlib.path import Path as PolygonPath
    import textwrap
    fig, ax = plt.subplots(figsize=(18,11))
    bounds=[]
    room_paths=[PolygonPath(np.asarray(world_input(r).pts)) for r in rooms]
    for room_index,room in enumerate(rooms):
        inp=world_input(room)
        info=lag_tegningsinfo(inp, beregn_prosjekt(inp), "Plantegning")
        thickness=PANEL_DB[inp.panel_key]['t']/1000
        if len(rooms)==1:
            plt.close(fig)
            return stramo_plan(inp.pts,inp.hoyde_m,inp.panelbredde_m,inp.dorer,info,
                               apninger=inp.apninger,wall_thickness=thickness,excluded_walls=inp.excluded_walls)
        stramo_plan(inp.pts,inp.hoyde_m,inp.panelbredde_m,inp.dorer,info,
                    apninger=inp.apninger,wall_thickness=thickness,excluded_walls=inp.excluded_walls,ax=ax,
                    dimension_obstacles=[p for i,p in enumerate(room_paths) if i!=room_index])
        pts=np.asarray(inp.pts)
        bounds.extend(floor_outline(pts,thickness))
        gx,gy=np.meshgrid(np.linspace(pts[:,0].min(),pts[:,0].max(),31),np.linspace(pts[:,1].min(),pts[:,1].max(),31))
        candidates=np.column_stack([gx.ravel(),gy.ravel()])
        candidates=candidates[PolygonPath(pts).contains_points(candidates,radius=-.01)]
        clearance=np.full(len(candidates),np.inf)
        for p,q in zip(pts,np.roll(pts,-1,axis=0)):
            edge=q-p;t=np.clip((candidates-p)@edge/(edge@edge),0,1)
            clearance=np.minimum(clearance,np.linalg.norm(candidates-p-t[:,None]*edge,axis=1))
        at=candidates[np.argmax(clearance)] if len(candidates) else pts.mean(axis=0)
        wrap = 9 if min(np.ptp(pts, axis=0)) < 3 else 24
        name = ax.text(*at,textwrap.fill(inp.navn,wrap),ha='center',va='center',fontsize=10,color='#07384c',
                bbox=dict(fc='white',ec='none',alpha=.9))
        name.set_gid('room-name')
        name._plan_candidates = candidates[np.argsort(-clearance)] if len(candidates) else [at]
        name._plan_room = PolygonPath(pts)
    if rooms:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        footprint = unary_union([Polygon(floor_outline(world_input(r).pts,
            PANEL_DB[world_input(r).panel_key]['t']/1000)) for r in rooms])
        info.update(navn="Tasty Fredrikstad" if all('Tasty' in r['input']['navn'] for r in rooms) else ' / '.join(project_name(r['input']['navn']) for r in rooms),
                    tnr='SAM-01', A=round(footprint.area,2), P=round(footprint.length,2))
        _tegn_fig_title_block(fig,info)
        pts=np.asarray(bounds);low,high=pts.min(axis=0),pts.max(axis=0)
        ax.set_xlim(low[0]-2.1,high[0]+2.1);ax.set_ylim(low[1]-2.1,high[1]+2.1)
    ax.set_title('Plantegning · Utvendige mål',color='#07384c',fontsize=14,fontweight='bold')
    ax.set_aspect('equal');ax.axis('off')
    fig.subplots_adjust(left=.02,right=.79,top=.94,bottom=.03)
    from drawing_2d import _dim_along_wall
    by_id = {room['id']: room for room in rooms}
    for room in rooms:
        placement = room.get('placement')
        if not placement or placement['target_id'] not in by_id:
            continue
        target = by_id[placement['target_id']]
        try:
            expected = snap_room(room, placement['wall'], target, placement['target_wall'],
                                 placement['distance_mm'], placement['from_end'])
            if not np.allclose(expected, room['position_mm'], atol=.01, rtol=0):
                continue  # Manual edits changed the relationship; never print a stale distance.
            start, end, _ = placement_points(room, target, placement['wall'],
                                             placement['target_wall'], placement['from_end'])
        except (ValueError, IndexError):
            continue
        winding = polygon_winding(world_input(target).pts) * (-1 if placement['from_end'] else 1)
        _dim_along_wall(ax, start, end, f"{np.linalg.norm(end-start)*1000:.0f} mm",
                        offset=.85, fs=10, winding=winding, total=True)
    if highlight and highlight[0] in by_id:
        target = by_id[highlight[0]]
        outer = np.asarray(floor_outline(world_input(target).pts, PANEL_DB[target['input']['panel_key']]['t']/1000))
        wall, from_end = highlight[1:]
        a,b = outer[wall], outer[(wall+1)%len(outer)]
        ax.plot([a[0],b[0]],[a[1],b[1]],color='#e0e000',linewidth=4,zorder=16)
        corner = b if from_end else a
        ax.plot(*corner,'o',mfc='white',mec='#07384c',ms=7,zorder=17)
        ax.annotate(f"H{(wall+1)%len(outer)+1 if from_end else wall+1}",corner,
                    xytext=(-12,-16),textcoords='offset points',ha='right',color='#07384c',
                    fontweight='bold',bbox=dict(fc='white',ec='none',pad=1),zorder=18)
    _arrange_assembly_labels(ax)
    return fig


def assembly_ui():
    st.subheader("Rom og sammenstilling")
    rooms = st.session_state["project_rooms"]
    if not rooms:
        st.info("Tegn et rom og trykk «Legg til ferdig rom». Gjenta for neste rom, og sett dem sammen her til slutt.")
        return
    labels = {r["id"]:f"{i+1}. {project_name(r['input']['navn']) or r['input']['rom_type']}" for i,r in enumerate(rooms)}
    controls, drawing = st.columns([1, 2.2], gap="large")
    highlight = None
    with controls:
        st.subheader("Plasser rom")
        if len(rooms)>1:
            moving_id = st.selectbox("Rom som skal flyttes", list(labels), format_func=labels.get, key="snap_moving")
            targets = [rid for rid in labels if rid != moving_id]
            if st.session_state.get('snap_target') not in targets:
                st.session_state['snap_target'] = targets[0]
            target_id = st.selectbox("Plasser mot rom", targets, format_func=labels.get, key="snap_target")
            moving = next(r for r in rooms if r['id']==moving_id)
            target = next(r for r in rooms if r['id']==target_id)
            signature = (moving_id, target_id, len(moving['input']['pts']), len(target['input']['pts']))
            if st.session_state.get('snap_signature') != signature:
                saved = moving.get('placement', {})
                if (saved.get('target_id') != target_id
                    or saved.get('wall', 0) >= len(moving['input']['pts'])
                    or saved.get('target_wall', 0) >= len(target['input']['pts'])):
                    saved = {}
                for key, value in (('snap_own_wall', saved.get('wall', 0)),
                                   ('snap_target_wall', saved.get('target_wall', 0)),
                                   ('snap_from_end', saved.get('from_end', False)),
                                   ('snap_distance', float(saved.get('distance_mm', 0)))):
                    st.session_state[key] = value
                st.session_state['snap_signature'] = signature
            from construction import floor_outline
            def wall_label(room, i):
                outer = floor_outline(world_input(room).pts, PANEL_DB[room['input']['panel_key']]['t']/1000)
                length = np.linalg.norm(np.subtract(outer[(i+1)%len(outer)], outer[i]))
                return f"Vegg {i+1} · {length*1000:.0f} mm"
            target_wall = st.selectbox("Vegg på hovedrom", range(len(target['input']['pts'])),
                format_func=lambda i, room=target: wall_label(room, i), key='snap_target_wall')
            own_wall = st.selectbox("Vegg på rommet som flyttes", range(len(moving['input']['pts'])),
                format_func=lambda i, room=moving: wall_label(room, i), key='snap_own_wall')
            corners = {False: f"H{target_wall+1} – start av veggen",
                       True: f"H{(target_wall+1)%len(target['input']['pts'])+1} – slutt av veggen"}
            from_end = st.selectbox("Mål fra utvendig hjørne", [False, True],
                format_func=corners.get, key='snap_from_end')
            distance = st.number_input("Avstand fra hjørne (mm)", min_value=0., max_value=1000000.,
                step=100., format='%.0f', key='snap_distance',
                help='Fra valgt utvendig hjørne til nærmeste utvendige hjørne på rommet som flyttes, målt langs veggen.')
            highlight = (target_id, target_wall, from_end)
            st.caption('Velg «Plasser rom» for å bruke avstanden. Rommet flyttes langs den valgte veggen.')
            if st.button('Plasser rom', key='snap_apply', use_container_width=True):
                try:
                    position = snap_room(moving, own_wall, target, target_wall, distance, from_end)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    moving['position_mm'] = position
                    moving['placement'] = dict(target_id=target_id, wall=own_wall,
                        target_wall=target_wall, from_end=from_end, distance_mm=distance)
                    st.session_state['pending_position'] = (moving_id, position)
                    st.rerun()
        else:
            st.caption('Legg til et rom til for å plassere rom mot hverandre.')
        with st.expander('Manuell plassering'):
            for room in rooms:
                rid = room['id']
                st.markdown(f"**{labels[rid]}**")
                c1,c2 = st.columns(2)
                x = c1.number_input('Venstre / høyre (mm)',value=float(room['position_mm'][0]),
                    min_value=-1000000.,max_value=1000000.,step=100.,format='%.0f',key=f'pos_{rid}_x')
                y = c2.number_input('Opp / ned (mm)',value=float(room['position_mm'][1]),
                    min_value=-1000000.,max_value=1000000.,step=100.,format='%.0f',key=f'pos_{rid}_y')
                if [x,y] != room['position_mm']:
                    room.pop('placement', None)
                room['position_mm'] = [x,y]
        with st.expander('Fellesvegger'):
            st.caption('Velg veggene som skal utelates etter at rommene er plassert. Fryseromsvegger beholdes som fellesvegger.')
            for room in rooms:
                rid = room['id']
                lengths = wall_lengths(room['input']['pts'])
                st.markdown(f"**{labels[rid]}**")
                room['excluded_walls'] = st.multiselect('Vegger som skal utelates', list(range(len(lengths))),
                    default=room['excluded_walls'], format_func=lambda i: f'Vegg {i+1}',key=f'omit_{rid}')
            matches = freezer_shared_walls(rooms)
            if matches:
                for cool,wall,freezer,fw in matches:
                    st.write(f"{labels[cool]} Vegg {wall+1} → {labels[freezer]} Vegg {fw+1}")
                if st.button('Bruk fryseromsvegger som fellesvegger',key='apply_shared_walls'):
                    affected = []
                    for cool,wall,_,_ in matches:
                        room = next(r for r in rooms if r['id']==cool)
                        room['excluded_walls'] = sorted(set(room['excluded_walls']+[wall]))
                        affected.append(cool)
                    st.session_state['pending_wall_controls'] = affected
                    st.rerun()
    with drawing:
        fig = assembly_plan(rooms, highlight=highlight)
        st.pyplot(fig)
        # Export the same measured positions, without the editor's selection marker.
        plt.close(fig)
        fig = assembly_plan(rooms)
        pdf = figur_som_pdf(fig, 'Plantegning')
        plt.close(fig)
        st.download_button('Last ned sammenstilling PDF',pdf,'sammenstilling.pdf','application/pdf')
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
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for i,room in enumerate(rooms):
            inp = world_input(room)
            archive.writestr(f"rom-{i+1}.ifc",gen_ifc(inp.pts,inp.hoyde_m,inp.navn,inp.panel_key,
                inp.dorer,inp.rom_type,inp.panelbredde_m,apninger=inp.apninger,excluded_walls=inp.excluded_walls))
    st.download_button("Last ned IFC-filer per rom (ZIP)",bundle.getvalue(),"rom-ifc.zip","application/zip")
    st.caption("IFC-filene har samme koordinatsystem og inneholder veggene som er valgt i sammenstillingen.")

