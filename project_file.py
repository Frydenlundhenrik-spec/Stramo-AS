"""Versioned, portable JSON projects. No executable or credential data."""
from dataclasses import asdict, replace
import base64
import copy
import json
import math
import uuid
import numpy as np
from database import PANEL_DB, DOR_DB, BESLAG_DB, FORM_MALER
from geometry import l_polygon, transform_polygon, validate_polygon, wall_lengths, polygon_winding, validate_wall_openings
from kalkulasjon import ProjectInput, beregn_prosjekt

FORMAT = "stramo-project"
VERSION = 1


def form_points(form):
    points = _form_points(form)
    dx, dy = form.get("origin_mm", [0, 0])
    return [(x+dx/1000, y+dy/1000) for x,y in points]


def _form_points(form):
    kind = form["kind"]
    if kind == "L-form":
        points = l_polygon(form["sides_mm"])
    elif kind == "Egendefinert polygon":
        points = [(x/1000,y/1000) for x,y in form["points_mm"]]
    else:
        points = FORM_MALER[kind]["func"](form["length_mm"]/1000, form["width_mm"]/1000,
                                        form.get("cut_x_mm",0)/1000, form.get("cut_y_mm",0)/1000)
    turns, mirrored = form.get("turns", 0), form.get("mirrored", False)
    # Identity must retain the coordinates of older custom polygons.
    return transform_polygon(points, turns, mirrored) if turns or mirrored else points


def make_room(inp, form, prices, background=None):
    return dict(id=uuid.uuid4().hex, input=asdict(replace(inp, excluded_walls=())),
                form=copy.deepcopy(form), prices=copy.deepcopy(prices),
                position_mm=[0,0], excluded_walls=[], background=background)


def number(value, low, high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Ugyldig tall. Forventet {low}–{high}.")
    return value


def integer(value, low, high):
    number(value,low,high)
    if not isinstance(value,int):
        raise ValueError("Forventet et heltall.")
    return value


def validate_room(room):
    if not isinstance(room,dict) or not isinstance(room.get("id"),str) or not 1 <= len(room["id"]) <= 64:
        raise ValueError("Rommet mangler gyldig ID.")
    data = room["input"]
    for key in ("navn","pnr","tnr","dato","maalestokk"):
        if not isinstance(data[key],str) or len(data[key]) > 300:
            raise ValueError(f"Ugyldig felt: {key}.")
    if data["rom_type"] not in ("Kjølerom","Fryserom") or data["panel_key"] not in PANEL_DB:
        raise ValueError("Ukjent romtype eller paneltype.")
    number(data["hoyde_m"],1.8,8)
    number(data["panelbredde_m"],.3,2)
    pts = data["pts"]
    if not isinstance(pts,list) or not 3 <= len(pts) <= 32:
        raise ValueError("Rommet må ha 3–32 hjørner.")
    for point in pts:
        if len(point) != 2:
            raise ValueError("Et hjørne må ha X og Y.")
        for value in point:
            number(value,-1000,1000)
    validate_polygon(pts)
    form = room["form"]
    if "thermal" in form:
        from thermal import validate_thermal_settings
        validate_thermal_settings(form["thermal"])
    kind = form["kind"]
    number(form.get("waste_pct",10),0,100)
    number(form.get("panel_kg_m2",0),0,500)
    integer(form.get("panel_stock_mm",0),0,30000)
    for field,default in (("plywood_width_mm",1500),("plywood_length_mm",3000)):
        integer(form.get(field,default),100,10000)
    accessories = form.get("accessory_quantities", {})
    if not isinstance(accessories, dict) or set(accessories) - {"fugemasse", "skum", "pakninger", "alarm"}:
        raise ValueError("Ugyldige tilbehørsmengder.")
    for key, value in accessories.items():
        if value is not None:
            number(value, 0, 1000000)
            if key != "pakninger" and value != int(value):
                raise ValueError("Antall tilbehør må være hele stykk.")
    if kind not in FORM_MALER:
        raise ValueError("Ukjent romform.")
    integer(form.get("turns", 0),0,3)
    if not isinstance(form.get("mirrored", False),bool):
        raise ValueError("Ugyldig speilvalg.")
    if kind == "L-form":
        if len(form["sides_mm"]) != 6:
            raise ValueError("L-formen må ha seks mål.")
        for value in form["sides_mm"]:
            integer(value,100,1000000)
    elif kind == "Egendefinert polygon":
        if not 3 <= len(form["points_mm"]) <= 16:
            raise ValueError("Egendefinert rom må ha 3–16 hjørner.")
        for point in form["points_mm"]:
            if len(point) != 2:
                raise ValueError("Ugyldig hjørne.")
            for value in point:
                number(value,-1000000,1000000)
    elif kind == "Femkant – avskåret hjørne":
        number(form["length_mm"],500,50000)
        number(form["width_mm"],500,30000)
        number(form["cut_x_mm"],50,form["length_mm"])
        number(form["cut_y_mm"],50,form["width_mm"])
        if type(form.get("diagonal_adjust_wall", 3)) is not int or form.get("diagonal_adjust_wall", 3) not in (1, 3):
            raise ValueError("Velg vegg 2 eller vegg 4 som nabovegg til skråveggen.")
    else:
        integer(form["length_mm"],500,50000)
        integer(form["width_mm"],500,30000)
    basis = form.get("dimension_basis", "internal")
    if basis not in ("internal", "external"):
        raise ValueError("Ukjent målgrunnlag.")
    origin = form.get("origin_mm", [0, 0])
    if not isinstance(origin, list) or len(origin) != 2:
        raise ValueError("Ugyldig formopprinnelse.")
    for value in origin:
        number(value, -1000000, 1000000)
    built = form_points(form)
    if basis == "external":
        from dimensions import inside_from_outside
        built = inside_from_outside(built, PANEL_DB[data["panel_key"]]["t"]/1000)
    if len(built) != len(pts) or not np.allclose(built,pts,atol=1e-8,rtol=0):
        raise ValueError("Rommets mål og geometri stemmer ikke overens i prosjektfilen.")
    if len(data["dorer"]) > 4 or len(data.get("apninger") or []) > 8:
        raise ValueError("For mange dører eller åpninger.")
    lengths = wall_lengths(pts)
    for door in data["dorer"]:
        if len(door) != 5 or door[0] not in DOR_DB or door[4] not in ("Venstre","Høyre"):
            raise ValueError("Ugyldig dør.")
        integer(door[1],0,10); integer(door[2],0,len(pts)-1); number(door[3],0,1000)
        width = DOR_DB[door[0]]["bw"]/1000
        if door[1] and door[3]+door[1]*width+(door[1]-1)*.2 > lengths[door[2]]+1e-6:
            raise ValueError("En dør ligger utenfor veggen.")
    for opening in data.get("apninger") or []:
        if len(opening) != 6 or not isinstance(opening[5],str) or len(opening[5]) > 300:
            raise ValueError("Ugyldig åpning.")
        integer(opening[0],0,len(pts)-1)
        # Stored distances use the inside corner; the editor shows outside distances.
        number(opening[1],0,10); number(opening[2],.1,5)
        number(opening[3],.1,3); number(opening[4],0,3)
        if opening[1]+opening[2] > lengths[opening[0]]+1e-6:
            raise ValueError("En åpning ligger utenfor veggen.")
    from construction import floor_depth
    validate_wall_openings(pts, data["hoyde_m"]-floor_depth(data["rom_type"]), data["dorer"], data.get("apninger"))
    if any(key not in BESLAG_DB for key in data["beslag_valg"]):
        raise ValueError("Ukjent beslag.")
    if len(room["position_mm"]) != 2:
        raise ValueError("Ugyldig plassering.")
    for value in room["position_mm"]:
        number(value,-1000000,1000000)
    if len(room["excluded_walls"]) != len(set(room["excluded_walls"])):
        raise ValueError("Dupliserte veggvalg.")
    for value in room["excluded_walls"]:
        integer(value,0,len(pts)-1)
    if not isinstance(room["prices"],dict) or len(room["prices"]) > 500:
        raise ValueError("Ugyldig prisliste.")
    for key,value in room["prices"].items():
        if not isinstance(key,str) or len(key)>300:
            raise ValueError("Ugyldig prisnøkkel.")
        number(value,0,1000000000)
    if data.get("excluded_walls"):
        raise ValueError("Veggvalg skal lagres i sammenstillingen, ikke i romtegningen.")
    background = room.get("background")
    if background is not None:
        raw = base64.b64decode(background["data"],validate=True)
        if len(raw)>10*1024*1024 or not isinstance(background["name"],str):
            raise ValueError("Bakgrunnsbildet er for stort eller ugyldig.")
        if not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")):
            raise ValueError("Bakgrunn må være PNG eller JPEG.")
    beregn_prosjekt(ProjectInput(**data),pris_override=room["prices"])
    return room


def encode_project(rooms, draft, active_id=None):
    project = dict(format=FORMAT,version=VERSION,rooms=rooms,draft=draft,active_id=active_id)
    validate_project(project)
    raw = json.dumps(project, ensure_ascii=False,allow_nan=False,indent=2).encode("utf-8")
    if len(raw) > 25*1024*1024:
        raise ValueError("Prosjektfilen kan være maksimalt 25 MB.")
    return raw


def validate_project(project):
    """Use identical checks for save and load so every saved file can reopen."""
    if project["format"] != FORMAT or project["version"] != VERSION:
        raise ValueError("Ukjent prosjektformat eller versjon.")
    if not isinstance(project["rooms"],list) or len(project["rooms"])>30:
        raise ValueError("Prosjektet kan ha maksimalt 30 rom.")
    for room in project["rooms"]:
        validate_room(room)
    ids = [r["id"] for r in project["rooms"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Prosjektet har dupliserte rom-ID-er.")
    validate_room(project["draft"])
    if project.get("active_id") is not None and project["active_id"] not in ids:
        raise ValueError("Det aktive rommet finnes ikke i prosjektet.")
    if project.get("active_id") is not None and project["draft"]["id"] != project["active_id"]:
        raise ValueError("Utkastets rom-ID stemmer ikke med det aktive rommet. Prosjektet er ikke åpnet.")
    if project.get("active_id") is None and project["draft"]["id"] in ids:
        raise ValueError("Utkastet er et lagret rom, men aktiv rom-ID mangler.")
    return project


def decode_project(raw):
    if len(raw)>25*1024*1024:
        raise ValueError("Prosjektfilen kan være maksimalt 25 MB.")
    try:
        def reject_constant(value):
            raise ValueError("Ugyldig tall i prosjektfilen.")
        project = json.loads(raw.decode("utf-8-sig"),parse_constant=reject_constant)
        return validate_project(project)
    except (KeyError,TypeError,IndexError,UnicodeError,OverflowError) as exc:
        raise ValueError("Prosjektfilen er ufullstendig eller har ugyldige felter.") from exc


def world_input(room):
    from branding import project_name
    data = copy.deepcopy(room["input"])
    data["navn"] = project_name(data["navn"])
    x,y = room["position_mm"]
    data["pts"] = [(a+x/1000,b+y/1000) for a,b in data["pts"]]
    data["excluded_walls"] = tuple(room["excluded_walls"])
    for field, default in (("plywood_width_mm", 1500), ("plywood_length_mm", 3000)):
        data[field] = room["form"].get(field, default)
    return ProjectInput(**data)


def wall_segment(room, index, outside=False):
    inp = world_input(room)
    a,b = np.array(inp.pts[index]),np.array(inp.pts[(index+1)%len(inp.pts)])
    direction = (b-a)/np.linalg.norm(b-a)
    inward = polygon_winding(inp.pts)*np.array([-direction[1],direction[0]])
    if outside:
        shift = -inward*PANEL_DB[inp.panel_key]["t"]/1000
        a,b = a+shift,b+shift
    return a,b,inward


def snap_room(room, wall, target, target_wall):
    """Align start along target direction, on outside face of retained target wall."""
    a,b,n = wall_segment(room,wall)
    c,d,m = wall_segment(target,target_wall,outside=True)
    if float(np.dot(n,m)) > -.999:
        raise ValueError("Veggene må vende mot hverandre. Roter/speil rommet før sammenstilling.")
    direction = (d-c)/np.linalg.norm(d-c)
    own_start = a if np.dot(a,direction)<np.dot(b,direction) else b
    target_start = c
    shift = target_start-own_start
    return [round(room["position_mm"][0]+shift[0]*1000,3),
            round(room["position_mm"][1]+shift[1]*1000,3)]


def freezer_shared_walls(rooms):
    """Only propose whole cooler walls fully covered by a retained freezer wall."""
    matches = []
    for cool in rooms:
        if cool["input"]["rom_type"] != "Kjølerom":
            continue
        for i in range(len(cool["input"]["pts"])):
            a,b,n = wall_segment(cool,i)
            for freezer in rooms:
                if freezer["input"]["rom_type"] != "Fryserom":
                    continue
                if freezer["input"]["hoyde_m"] < cool["input"]["hoyde_m"]:
                    continue
                for j in range(len(freezer["input"]["pts"])):
                    if j in freezer["excluded_walls"]:
                        continue
                    c,d,m = wall_segment(freezer,j,outside=True)
                    if np.dot(n,m)>-.999:
                        continue
                    direction = (d-c)/np.linalg.norm(d-c)
                    if max(abs(np.dot(a-c,m)),abs(np.dot(b-c,m)))>.001:
                        continue
                    projections = [np.dot(a-c,direction),np.dot(b-c,direction)]
                    # Coverage follows the actual square-jointed wall, including omitted neighbours.
                    from construction import wall_outer_face_span
                    thickness = PANEL_DB[freezer["input"]["panel_key"]]["t"]/1000
                    lo,hi=wall_outer_face_span(world_input(freezer).pts,j,thickness,freezer["excluded_walls"])
                    if min(projections)>=lo-.001 and max(projections)<=hi+.001:
                        matches.append((cool["id"],i,freezer["id"],j))
    return matches
