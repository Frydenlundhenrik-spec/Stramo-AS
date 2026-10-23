"""Analytic and assembly regressions for transmission calculations."""
import copy
import json
import math
from pathlib import Path

from thermal import (PANEL_U, calculate_project, calculate_room, condensation_check,
                     panel_u, thermal_settings, validate_thermal_settings)


template = json.loads(Path(__file__).with_name("Tasty-Rom4-og-fryserom-med-dorer.json").read_text(encoding="utf-8"))["rooms"]


def rectangle(freezer=False):
    room = copy.deepcopy(template[int(freezer)])
    room["id"] = "freezer" if freezer else "cooler"
    room["input"]["pts"] = [(0,0),(4,0),(4,3),(0,3)]
    room["input"]["dorer"] = []
    room["input"]["apninger"] = []
    room["position_mm"] = [0,0]
    room["excluded_walls"] = []
    room["form"]["thermal"] = dict(conditions_confirmed=True, floor_u=.5, door_u=1.2)
    return room


def near(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8), (actual,expected)


def rejected(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("Invalid data was accepted")


room = rectangle()
r = calculate_room(room)
near(r["known_net_w"], .29*(14*2.4+12)*13 + .5*12*10)
assert r["complete"] and r["unknown_surface_count"] == 0
near(sum(s["area_m2"] for s in r["surfaces"]), 14*2.4+24)
assert PANEL_U == {"PIR 80 mm": .29, "PIR 100 mm": .22, "PIR 120 mm": .19}
assert thermal_settings({"input":{"rom_type":"Kjølerom"}})["ambient_c"] == 18

# Replace exactly the door area, keeping total enclosure area fixed.
door_key = template[0]["input"]["dorer"][0][0]
room["input"]["dorer"] = [[door_key,1,0,.4,"Høyre"]]
d = calculate_room(room)
near(d["known_net_w"]-r["known_net_w"], (1.2-.29)*2.1*13)
near(sum(s["area_m2"] for s in d["surfaces"]), 14*2.4+24)
room["input"]["apninger"] = [[1,.5,.5,.5,1,"Ventilasjon"]]
opened = calculate_room(room)
assert not opened["complete"]
near(opened["unknown_area_m2"], .25)
near(opened["known_net_w"], d["known_net_w"]-.25*.29*13)

# Missing data is explicit, even when the adjacent temperatures coincide.
room = rectangle()
room["form"]["thermal"] = {}
room["input"]["dorer"] = [[door_key,1,0,.4,"Høyre"]]
incomplete = calculate_room(room)
near(incomplete["unknown_area_m2"], 12+2.1)
assert not incomplete["complete"]
room["form"]["thermal"]["inside_c"] = 18
assert calculate_room(room)["unknown_area_m2"] == incomplete["unknown_area_m2"]

# The unlisted 150 mm standard panel is never substituted by FROST/ROOF data.
room = rectangle()
room["input"]["panel_key"] = "PIR 150 mm"
assert panel_u(room) is None
unknown = calculate_room(room)
near(unknown["unknown_area_m2"], 14*2.4+12)
room["form"]["thermal"]["panel_u"] = .15
assert calculate_room(room)["complete"]

# The removed cooler wall reuses actual freezer panel/door area at correct height.
rooms = copy.deepcopy(template)
for room in rooms:
    room["form"]["thermal"] = dict(conditions_confirmed=True, door_u=1.2, floor_u=.5)
project = calculate_project(rooms)
near(project["shared_net_w"], 0)
near(sum(r["known_net_w"] for r in project["rooms"]), project["known_net_w"])
cool, freeze = project["rooms"]
for room, result in zip(rooms,project["rooms"]):
    from geometry import poly_area, poly_perim
    expected = poly_perim(room["input"]["pts"])*room["input"]["hoyde_m"] + 2*poly_area(room["input"]["pts"])
    near(sum(s["area_m2"] for s in result["surfaces"]), expected)
assert cool["known_negative_w"] < 0
assert cool["unknown_area_m2"] > 0, "Elevated freezer/corner gaps must be unresolved"
assert not project["complete"]
cool_shared = [s for s in cool["surfaces"] if s["shared"]]
freeze_shared = [s for s in freeze["surfaces"] if s["shared"]]
near(sum(s["area_m2"] for s in cool_shared),sum(s["area_m2"] for s in freeze_shared))
assert any(s["u"] == 1.2 for s in cool_shared), "Shared freezer doors must replace panel area"
assert all(s["u"] in (.22,1.2) for s in cool_shared)
near(sum(s["watts"] for s in cool_shared), -sum(s["watts"] for s in freeze_shared))

# Translation cannot change shared areas or thermal totals.
shifted = copy.deepcopy(rooms)
for room in shifted:
    room["position_mm"] = [room["position_mm"][0]+7350, room["position_mm"][1]-2350]
shifted_result = calculate_project(shifted)
near(shifted_result["known_net_w"], project["known_net_w"])
near(shifted_result["unknown_area_m2"], project["unknown_area_m2"])
duplicate = copy.deepcopy(rooms[1]); duplicate["id"] = "duplicate-freezer"
rejected(lambda: calculate_project(rooms+[duplicate]))

# A confirmed room must not silently inherit an unconfirmed neighboring room.
unconfirmed = copy.deepcopy(rooms)
unconfirmed[0]["form"]["thermal"]["conditions_confirmed"] = False
assert calculate_project(unconfirmed)["rooms"][1]["complete"] is False
assert any("ubekreftede" in w for w in calculate_project(unconfirmed)["rooms"][1]["warnings"])

# Retaining the cooler wall means no shared-wall transfer is assumed.
rooms[0]["excluded_walls"] = []
assert not any(s["shared"] for r in calculate_project(rooms)["rooms"] for s in r["surfaces"])

# Manual removals and retained-wall apertures are unresolved, not zero heat flow.
room = rectangle(True)
room["excluded_walls"] = [0]
near(calculate_room(room)["unknown_area_m2"],4*2.4)
room = rectangle()
room["form"]["thermal"]["heat_flux_limit"] = 3.5
comparison = calculate_room(room)["panel_comparison"]
assert comparison[0]["meets_flux_limit"] is False and comparison[1]["meets_flux_limit"] is True
near(comparison[0]["max_abs_heat_flux_w_m2"], .29*13)

for bad in ({"inside_c":float("nan")}, {"door_u":0}, {"rh_pct":101}, {"panel_u":True},
            {"conditions_confirmed":1}, {"heat_flux_limit":-1}, {"unexpected":1}, []):
    rejected(lambda bad=bad: validate_thermal_settings(bad))
near(condensation_check(18,-18,60,.22)["surface_c"], 18-.22*36*.13)
assert condensation_check(18,-18,100,.22)["condensation_risk"]
rejected(lambda: condensation_check(18,-18,60,float("inf")))
rejected(lambda: condensation_check(18,-18,60,10))
print("PASS: analytic heat flow, cutouts, shared areas and signed cancellation, missing data, product U values and validation")
