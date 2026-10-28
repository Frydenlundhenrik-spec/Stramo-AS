"""Unrounded installation needs; order rounding happens once for the chosen scope."""
import math
from construction import fixing_screw_count
from geometry import poly_area

# key: display name, order unit, price per order unit, contents per order unit
CATALOG = {
    "skruer_eske": ("22 mm hvite skruer", "eske à 500", 0, 500),
    "gulvskrue": ("22 mm grå gulvskrue", "stk", 0, 1),
    "silikon_hvit": ("Silikon hvit", "tube", 0, 1),
    "silikon_gra": ("Silikon grå", "tube", 0, 1),
    "skum": ("Skum", "flaske", 0, 1),
    "alarm": ("Alarm", "stk", 4000, 1),
    "pvc_gardin": ("PVC gardin", "stk", 5000, 1),
}


def accessory_needs(pts, height, room_type, thickness, doors, cut_list, excluded_walls=()):
    """Only installed faces count; board area is the clear interior footprint."""
    freezer = room_type == "Fryserom"
    panels = cut_list[cut_list.Elementnavn.str.startswith(("V", "T", "G"))]
    area = float(panels.Areal_m2.sum())
    needs = dict(skruer_eske=fixing_screw_count(pts, height, room_type, thickness, excluded_walls),
                 silikon_hvit=area/(5 if freezer else 15))
    if freezer:
        corners = 0
        for i, p in enumerate(pts):
            if i in excluded_walls or (i-1)%len(pts) in excluded_walls:
                continue
            a, b = pts[i-1], pts[(i+1)%len(pts)]
            if abs((p[0]-a[0])*(b[1]-p[1])-(p[1]-a[1])*(b[0]-p[0])) > 1e-9:
                corners += 1
        area = poly_area(pts)
        needs.update(gulvskrue=10*area, silikon_gra=.5*area, skum=.5*corners,
                     alarm=1, pvc_gardin=sum(d[1] for d in doors))
    return needs


def order_quantities(needs):
    return {key: math.ceil(value/CATALOG[key][3]-1e-9) for key, value in needs.items()}


def project_accessories(rooms):
    from project_file import world_input
    from kalkulasjon import beregn_prosjekt
    totals = {}
    for room in rooms:
        result = beregn_prosjekt(world_input(room), pris_override=room.get("prices"))
        for key, value in result["accessory_needs"].items():
            totals[key] = totals.get(key, 0) + value
    return order_quantities(totals)
