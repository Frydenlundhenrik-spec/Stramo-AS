"""Checks through the room calculator, orders and transport for non-square bends."""
from dataclasses import replace
from pathlib import Path
import re

from construction import fixing_screw_count, screws_per_trim_piece, wall_span
from cutlist_pdf import project_materials
from finishing import sloped_corner_profiles, sloped_trim_name, trim_cuts
from geometry import beslag_beregning, corner_bend_degrees, transform_polygon
from kalkulasjon import beregn_prosjekt
from project_file import decode_project, make_room, world_input
from transport import packages


def specials(points, excluded=()):
    bb = beslag_beregning(points, 2.4, excluded, .08)
    return {(p["side"], tuple(p["corners"])): p for p in bb["special_profiles"]}


pentagon = [(0, 0), (4, 0), (4, 2), (2, 3), (0, 3)]
for mirrored in (False, True):
    for turns in range(4):
        pts = transform_polygon(pentagon, turns, mirrored)
        profiles = specials(pts)
        assert len(profiles) == 4
        for side in ("inner", "outer"):
            assert 63.4349 < corner_bend_degrees(pts, 2) < 63.4350
            assert 26.5650 < corner_bend_degrees(pts, 3) < 26.5651
            assert profiles[side, (3,)]["angle"] == 116
            assert profiles[side, (4,)]["angle"] == 153
            assert not profiles[side, (3,)]["reentrant"]
        assert not specials(pts, excluded=(2,))  # Omit the diagonal wall.
        assert {key[1] for key in specials(pts, excluded=(1,))} == {(4,)}

equal = [(0,0), (4,0), (4,2), (3,3), (0,3)]
for profile in specials(equal).values():
    assert profile["angle"] == 135 and profile["corners"] == [3, 4] and profile["qty"] == 3
octagon = [(1,0),(2,0),(3,1),(3,2),(2,3),(1,3),(0,2),(0,1)]
for profile in beslag_beregning(octagon, 1.8)["special_profiles"]:
    assert len(profile["cuts"]) == profile["qty"] == 8  # Seven bars would cover net LM + 10%, but not eight cuts.
concave = [(0,0),(4,0),(4,4),(2,4),(2,2),(1,3),(0,3)]
assert specials(concave)["inner", (5,)]["reentrant"]
assert not specials([(0,0),(4,0),(4,4),(0,4)])
with_seam = [(0,0),(2,0),(4,0),(4,4),(0,4)]
assert beslag_beregning(with_seam, 2.4)["n_inn"] == 4  # Collinear point has no corner trim.

# Independent accounting: five inner and five outer corner pieces (all 2400 mm).
bb = beslag_beregning(pentagon, 2.4, thickness=.08)
for suffix in ("inn", "ut"):
    cuts = " / ".join(row["Kapp"] for row in bb[f"kapp_{suffix}"])
    for n in (3, 4):
        assert f"H{n} vegg" not in cuts
    for n in (1, 2, 5):
        assert f"H{n} vegg" in cuts
expected = 10 * screws_per_trim_piece(2400)
for bar in bb["kapp_inn"] + bb["kapp_ut"]:
    expected += sum(screws_per_trim_piece(int(mm)) for mm in re.findall(r"(\d+) mm \(V\d+ tak\)", bar["Kapp"]))
spans = [wall_span(pentagon, i, .08) for i in range(5)]
channels = trim_cuts([("U", end-start) for start,end in spans])
for bar in channels:
    expected += sum(screws_per_trim_piece(int(mm)) for mm in re.findall(r"(\d+) mm \(U\)", bar["Kapp"]))
assert fixing_screw_count(pentagon, 2.4, "Kjølerom", .08) == expected

source = decode_project(Path("Tasty-Rom4-og-fryserom-med-dorer.json").read_bytes())["rooms"][0]
inp = replace(world_input(source), pts=pentagon, navn="Skrå 1", hoyde_m=2.4, dorer=[], apninger=[],
              excluded_walls=(), shared_walls=())
rooms = [make_room(replace(inp, navn=name), source["form"], {}) for name in ("Skrå 1", "Skrå 2")]
order = project_materials(rooms)
order = order[order.Profil_side.notna()]
assert len(order) == 4 and set(order.Gruppe) == {"Beslag"}
assert sorted(order.Profilvinkel_grad) == [116, 116, 153, 153]
assert not order.Profil_inntrukket.any()
assert all("Skrå 1: H" in refs and "Skrå 2: H" in refs for refs in order.Profil_hjorner)
calc = beregn_prosjekt(inp)["df_mat"]
colli = packages(rooms)
for row in order.itertuples():
    product = row.Produkt.split(" · 0,6 mm")[0]
    assert calc.loc[calc.Post.eq(product), "Mengde"].sum() * 2 == row.Stk == 4
    assert row.Løpemeter == 2.5 * row.Stk
    assert colli.loc[colli.Innhold.eq(row.Produkt), "Antall"].sum() == row.Stk
# Same workshop bend combines cuts, but opposite folds and truly right corners stay separate.
mixed = sloped_corner_profiles([(0,44.8),(1,45.0),(2,45.001),(3,-44.8),(4,89.9),
                                (5,90),(6,.001),(7,179.6)], 2.4, 2.4)
inner = {tuple(p["corners"]): p for p in mixed if p["side"] == "inner"}
assert inner[1,2]["angle"] == 135 and inner[1,2]["qty"] == 3
assert inner[3,]["angle"] == 134 and inner[4,]["reentrant"]
assert inner[5,]["angle"] == 90 and (6,) not in inner
assert inner[7,]["angle"] == 179 and inner[8,]["angle"] == 0
assert inner[3,]["product"] == sloped_trim_name("inner", 45.001)
assert "knekk fra flat plate 46°" in inner[3,]["product"]
print("PASS: whole-degree workshop bends, groupings, screw counts, cutting, purchase and transport")
