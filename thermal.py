"""Stationary transmission estimate on the rooms' internal reference surfaces.

Published PIR STANDARD Uc values include the panel joints/standard fasteners.
This is not a refrigeration-load or structural design calculation. Doors,
open penetrations, ground and manual wall removals are never assumed adiabatic.
"""
import math
from collections import defaultdict

import numpy as np

from construction import finished_floor, wall_base
from database import DOR_DB
from geometry import poly_area, validate_polygon, validate_wall_openings, wall_lengths


PANEL_U = {"PIR 80 mm": .29, "PIR 100 mm": .22, "PIR 120 mm": .19}
SOURCE = "BALEX PIR STANDARD produktdatablad side 3–4 / teknisk katalog side 26"
LIMIT_SOURCE = "Valgfri prosjektgrense for varmefluks; ikke et generelt forskriftskrav."
_RANGES = {"inside_c": (-60, 60), "ambient_c": (-60, 80),
           "ceiling_c": (-60, 80), "ground_c": (-40, 60), "rh_pct": (1, 100),
           "door_u": (.01, 20), "floor_u": (.01, 20), "panel_u": (.01, 20),
           "heat_flux_limit": (.1, 100)}
_OPTIONAL = {"door_u", "floor_u", "panel_u", "heat_flux_limit"}
EPS = 1e-8


def validate_thermal_settings(settings):
    """Validate a stored, possibly partial settings dictionary without defaults."""
    if not isinstance(settings, dict):
        raise ValueError("Varmeberegningens innstillinger må være et objekt.")
    for key, value in settings.items():
        if key == "conditions_confirmed":
            if not isinstance(value, bool):
                raise ValueError("Bekreftelse av temperaturgrunnlag må være sann/usann.")
        elif key in _RANGES:
            if value is None and key in _OPTIONAL:
                continue
            low, high = _RANGES[key]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not low <= value <= high):
                raise ValueError(f"Ugyldig varmeberegningsverdi {key}: forventet {low}–{high}.")
        else:
            raise ValueError(f"Ukjent varmeberegningsfelt: {key}.")
    return dict(settings)


def thermal_settings(room):
    settings = dict(inside_c=-18.0 if room["input"]["rom_type"] == "Fryserom" else 5.0,
                    ambient_c=18.0, ceiling_c=18.0, ground_c=15.0, rh_pct=60.0,
                    conditions_confirmed=False, door_u=None, floor_u=None,
                    panel_u=None, heat_flux_limit=None)
    settings.update(validate_thermal_settings(room.get("form", {}).get("thermal", {})))
    return settings


def panel_u(room):
    override = thermal_settings(room)["panel_u"]
    return override if override is not None else PANEL_U.get(room["input"]["panel_key"])


def dew_point(temperature_c, rh_pct):
    """Magnus approximation over water, intended for the warm side (0–60 C)."""
    for value, low, high in ((temperature_c, 0, 60), (rh_pct, 1, 100)):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not low <= value <= high):
            raise ValueError("Duggpunktanslaget krever 0–60 °C og 1–100 % RF.")
    alpha = math.log(rh_pct / 100) + 17.62 * temperature_c / (243.12 + temperature_c)
    return 243.12 * alpha / (17.62 - alpha)


def condensation_check(warm_c, cold_c, rh_pct, u, surface_resistance=.13):
    """Plane-field screening only; cannot verify corners, thresholds or joints."""
    if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                for v in (warm_c, cold_c, u, surface_resistance))
            or cold_c > warm_c or not -60 <= cold_c <= 60
            or not .01 <= u <= 20 or not 0 < surface_resistance <= .3
            or u*surface_resistance >= 1):
        raise ValueError("Ugyldig grunnlag for kondensanslag.")
    dew = dew_point(warm_c, rh_pct)
    surface = warm_c - u * (warm_c - cold_c) * surface_resistance
    return dict(dew_point_c=dew, surface_c=surface, margin_c=surface-dew,
                condensation_risk=surface <= dew,
                note="Forenklet anslag i plant felt, Rsi=0,13 m²K/W som standard. "
                     "Kuldebroer og luftlekkasjer er ikke kontrollert.")


def _rect_intersection(a, b):
    r = (max(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), min(a[3], b[3]))
    return r if r[1]-r[0] > EPS and r[3]-r[2] > EPS else None


def _inside(rect, x, z):
    return rect[0]-EPS <= x <= rect[1]+EPS and rect[2]-EPS <= z <= rect[3]+EPS


def _cells(bounds, rectangles):
    """Exact rectangular partition for apertures/shared-wall patches."""
    xs, zs = {bounds[0], bounds[1]}, {bounds[2], bounds[3]}
    for r in rectangles:
        clipped = _rect_intersection(bounds, r)
        if clipped:
            xs.update(clipped[:2]); zs.update(clipped[2:])
    xs, zs = sorted(xs), sorted(zs)
    for x1, x2 in zip(xs, xs[1:]):
        for z1, z2 in zip(zs, zs[1:]):
            if x2-x1 > EPS and z2-z1 > EPS:
                yield (x1, x2, z1, z2), (x1+x2)/2, (z1+z2)/2


def _openings(room, wall):
    data = room["input"]
    floor = finished_floor(data["rom_type"], data["panel_key"])
    result = []
    for index, door in enumerate(data["dorer"]):
        if len(door) < 4:
            if door[1]:
                raise ValueError("Varmeberegning krever vegg og plassering for alle dører.")
            continue
        key, count, side, offset = door[:4]
        if side == wall:
            width, height = DOR_DB[key]["bw"]/1000, DOR_DB[key]["bh"]/1000
            for n in range(count):
                left = offset+n*(width+.2)
                result.append(((left, left+width, floor, floor+height),
                               "door", f"Dør {index+1}.{n+1}"))
    for index, opening in enumerate(data.get("apninger") or []):
        side, left, width, height, sill, label = opening
        if side == wall:
            result.append(((left, left+width, floor+sill, floor+sill+height),
                           "opening", f"Åpning {index+1}: {label}"))
    return result


def _row(surface, area, u, neighbor, inside, note, shared=False, panel_room_id=None):
    delta = neighbor-inside if neighbor is not None else None
    return dict(surface=surface, area_m2=area, u=u, neighbor_c=neighbor,
                delta_t=delta, watts=u*area*delta if u is not None and delta is not None else None,
                note=note, shared=shared, panel_room_id=panel_room_id)


def _compress(rows):
    grouped = {}
    for row in rows:
        key = tuple(row[k] for k in ("surface", "u", "neighbor_c", "note", "shared", "panel_room_id"))
        if key not in grouped:
            grouped[key] = dict(row)
        else:
            grouped[key]["area_m2"] += row["area_m2"]
            if row["watts"] is not None:
                grouped[key]["watts"] += row["watts"]
    return list(grouped.values())


def _totals(rows):
    return dict(known_positive_w=sum(max(0, r["watts"]) for r in rows if r["watts"] is not None),
                known_negative_w=sum(min(0, r["watts"]) for r in rows if r["watts"] is not None),
                known_net_w=sum(r["watts"] for r in rows if r["watts"] is not None),
                unknown_area_m2=sum(r["area_m2"] for r in rows if r["watts"] is None),
                unknown_surface_count=sum(r["watts"] is None for r in rows))


def calculate_project(rooms):
    """Calculate signed heat into each room; shared transfers cancel in the sum.

    The supported assembly is a removed cooler wall against a retained freezer
    wall. Corner extensions and missing elevation strips are marked unknown,
    not extended or silently closed. All area measurements use internal planes.
    Room records follow project_file.validate_room's validated project schema.
    """
    # Lazy import lets project_file use validate_thermal_settings safely.
    from project_file import freezer_shared_walls, wall_segment

    ids = [r["id"] for r in rooms]
    if len(set(ids)) != len(ids):
        raise ValueError("Rom-ID-er må være unike i varmeberegningen.")
    by_id = {r["id"]: r for r in rooms}
    settings = {r["id"]: thermal_settings(r) for r in rooms}
    raw = {key: [] for key in ids}
    warnings = {key: [] for key in ids}
    neighbors = {key: set() for key in ids}
    for room in rooms:
        data = room["input"]
        validate_polygon(data["pts"])
        if not math.isfinite(data["hoyde_m"]) or not 1.8 <= data["hoyde_m"] <= 8:
            raise ValueError("Ugyldig romhøyde i varmeberegningen.")
        validate_wall_openings(data["pts"], data["hoyde_m"]-(.012 if data["rom_type"] == "Fryserom" else 0),
                               data["dorer"], data.get("apninger"))
        if not settings[room["id"]]["conditions_confirmed"]:
            warnings[room["id"]].append("Temperaturer, RF og randbetingelser er ikke bekreftet; standardverdier er forutsetninger.")
        if panel_u(room) is None:
            warnings[room["id"]].append("Dokumentert U-verdi mangler for valgt panel. Legg inn dokumentert verdi.")

    # Store freezer-plane rectangles plus the affine map back to the cooler wall.
    shared = defaultdict(list)
    covered = defaultdict(list)
    planned_cooler_coverage = defaultdict(list)
    for cool_id, cw, freeze_id, fw in freezer_shared_walls(rooms):
        cool, freeze = by_id[cool_id], by_id[freeze_id]
        if cw not in cool["excluded_walls"]:
            continue
        a, b, _ = wall_segment(cool, cw)
        c, d, _ = wall_segment(freeze, fw, outside=True)
        direction = (d-c)/np.linalg.norm(d-c)
        cool_direction = (b-a)/np.linalg.norm(b-a)
        start = float(np.dot(a-c, direction))
        slope = float(np.dot(cool_direction, direction))
        end = float(np.dot(b-c, direction))
        cz = wall_base(cool["input"]["rom_type"], cool["input"]["panel_key"])
        fz = wall_base(freeze["input"]["rom_type"], freeze["input"]["panel_key"])
        bounds = (0, float(np.linalg.norm(d-c)), fz, fz+freeze["input"]["hoyde_m"])
        rect = _rect_intersection(bounds, (min(start,end), max(start,end), cz, cz+cool["input"]["hoyde_m"]))
        if rect:
            neighbors[cool_id].add(freeze_id)
            neighbors[freeze_id].add(cool_id)
            mapped = sorted(((rect[0]-start)/slope, (rect[1]-start)/slope))
            cool_rect = (*mapped, rect[2], rect[3])
            if any(_rect_intersection(cool_rect, prior) for prior in planned_cooler_coverage[(cool_id,cw)]):
                raise ValueError("Flere fryservegger dekker samme kjølevegg. Kontroller sammenstillingen.")
            planned_cooler_coverage[(cool_id,cw)].append(cool_rect)
            shared[(freeze_id,fw)].append(dict(rect=rect, cool_id=cool_id, wall=cw, start=start, slope=slope))
    for patches in shared.values():
        for index, p in enumerate(patches):
            if any(_rect_intersection(p["rect"], q["rect"]) for q in patches[:index]):
                raise ValueError("Flere kjølerom overlapper samme fellesvegg. Kontroller sammenstillingen.")

    for room in rooms:
        rid, data, cfg = room["id"], room["input"], settings[room["id"]]
        z0 = wall_base(data["rom_type"], data["panel_key"])
        for wall, length in enumerate(wall_lengths(data["pts"])):
            if wall in room["excluded_walls"]:
                continue
            holes = _openings(room, wall)
            patches = shared[(rid,wall)]
            bounds = (0, length, z0, z0+data["hoyde_m"])
            for rect, x, z in _cells(bounds, [h[0] for h in holes]+[p["rect"] for p in patches]):
                hole = next((h for h in holes if _inside(h[0],x,z)), None)
                patch = next((p for p in patches if _inside(p["rect"],x,z)), None)
                area = (rect[1]-rect[0])*(rect[3]-rect[2])
                owner = rid if hole is None else None
                if hole:
                    u = cfg["door_u"] if hole[1] == "door" else None
                    label = hole[2]
                    note = (("U-verdi for hele døren inkludert karm mangler." if u is None else
                             "Manuelt angitt U-verdi for hele døren inkludert karm.") if hole[1] == "door" else
                            "Åpning: lukking og varme-/luftstrøm er ukjent.")
                else:
                    u, label, note = panel_u(room), "Panel", SOURCE if cfg["panel_u"] is None else "Manuelt angitt U-verdi for panel."
                neighbor = settings[patch["cool_id"]]["inside_c"] if patch else cfg["ambient_c"]
                raw[rid].append(_row(f"V{wall+1} – {label}", area, u, neighbor, cfg["inside_c"], note,
                                     bool(patch), owner))
                if patch:
                    cool_id = patch["cool_id"]
                    mapped = sorted(((rect[0]-patch["start"])/patch["slope"],
                                     (rect[1]-patch["start"])/patch["slope"]))
                    covered[(cool_id,patch["wall"])].append((*mapped,rect[2],rect[3]))
                    raw[cool_id].append(_row(f"V{patch['wall']+1} – felles {label.lower()}", area, u,
                                             cfg["inside_c"], settings[cool_id]["inside_c"],
                                             f"Bruker fryserommets {label.lower()}. "+note, True, owner))

    for room in rooms:
        rid, data, cfg = room["id"], room["input"], settings[room["id"]]
        z0 = wall_base(data["rom_type"], data["panel_key"])
        for wall in room["excluded_walls"]:
            bounds = (0, wall_lengths(data["pts"])[wall], z0, z0+data["hoyde_m"])
            covers = covered[(rid,wall)]
            for rect, x, z in _cells(bounds, covers):
                if not any(_inside(c,x,z) for c in covers):
                    raw[rid].append(_row(f"V{wall+1} – uavklart veggparti", (rect[1]-rect[0])*(rect[3]-rect[2]),
                                         None, None, cfg["inside_c"],
                                         "Fjernet vegg uten dokumentert dekning i bredde/høyde; lukking og randbetingelse må avklares."))
            if covers:
                warnings[rid].append(f"V{wall+1}: fellesvegg avgrenset til faktisk overlapp; hjørneforlengelser/gulv- og taktilslutninger er ikke dokumentert.")
                if _openings(room,wall):
                    warnings[rid].append(f"V{wall+1}: dører/åpninger i fjernet kjølevegg brukes ikke; beholdt fryservegg styrer.")
        area = poly_area(data["pts"])
        raw[rid].append(_row("Tak", area, panel_u(room), cfg["ceiling_c"], cfg["inside_c"],
                             "Innvendig referanseareal; panelverdi, uten særskilt beregning av kanttilslutninger.", panel_room_id=rid))
        freezer = data["rom_type"] == "Fryserom"
        raw[rid].append(_row("Gulv", area, panel_u(room) if freezer else cfg["floor_u"], cfg["ground_c"], cfg["inside_c"],
                             "Panelbasert anslag; lekter/fiberplate og grunnen er ikke lagberegnet." if freezer else
                             "Eksisterende gulv: U-verdi og temperatur på andre siden må dokumenteres.", panel_room_id=rid if freezer else None))

    result = []
    for room in rooms:
        rid = room["id"]
        rows = _compress(raw[rid])
        totals = _totals(rows)
        owned = [r for r in rows if r["panel_room_id"] == rid and r["delta_t"] is not None]
        max_delta = max((abs(r["delta_t"]) for r in owned), default=0)
        limit = settings[rid]["heat_flux_limit"]
        comparison = [dict(thickness_mm=int(key.split()[1]), u=u,
                           max_abs_heat_flux_w_m2=u*max_delta,
                           known_panel_net_w=sum(r["area_m2"]*r["delta_t"]*u for r in owned),
                           meets_flux_limit=None if limit is None else u*max_delta <= limit)
                      for key,u in PANEL_U.items()]
        unconfirmed_neighbors = [key for key in neighbors[rid] if not settings[key]["conditions_confirmed"]]
        if unconfirmed_neighbors:
            names = ", ".join(by_id[key]["input"]["navn"] for key in sorted(unconfirmed_neighbors))
            warnings[rid].append(f"Fellesvegg bruker ubekreftede temperaturforutsetninger fra: {names}.")
        result.append(dict(id=rid, name=room["input"]["navn"], settings=settings[rid], surfaces=rows,
                           **totals, complete=totals["unknown_surface_count"] == 0
                           and settings[rid]["conditions_confirmed"] and not unconfirmed_neighbors,
                           warnings=warnings[rid], panel_comparison=comparison))
    rows = [row for r in result for row in r["surfaces"]]
    totals = _totals(rows)
    return dict(rooms=result, **totals, complete=all(r["complete"] for r in result),
                shared_net_w=sum(r["watts"] for r in rows if r["shared"] and r["watts"] is not None),
                warnings=["Kun stasjonær transmisjon på innvendige referanseflater. Døråpning/luftutskifting, varer, personer, lys, vifter og avriming er ikke med. "
                          "Kjent netto varme er ikke samlet dimensjonerende kjølebehov. Ukjente arealer summeres per romside."])


def calculate_room(room):
    return calculate_project([room])["rooms"][0]
