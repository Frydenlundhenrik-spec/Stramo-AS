from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from geometry import l_polygon, wall_lengths, door_dimensions
from drawing_2d import stramo_plan, tegn_veggoppstalt, wall_panel_polygon
from construction import wall_polygon
from shapely.geometry import Polygon
from shapely.ops import unary_union


def check():
    initial = [6000, 2500, 3500, 2000, 2500, 4500]
    # Both orientations and all cyclic starting sides preserve entered lengths.
    for seed in (initial, [8720,6685,4860,2410,3860,9095],
                 [8720,9095,4860,2410,3860,6685]):
        for shift in range(6):
            sides = seed[shift:] + seed[:shift]
            original = sides.copy()
            points = l_polygon(sides)
            assert sides == original
            assert np.allclose(np.array(wall_lengths(points))*1000,sides)
    left_high = l_polygon([8720,6685,4860,2410,3860,9095])
    right_high = l_polygon([8720,9095,4860,2410,3860,6685])
    assert left_high[4][1] > left_high[2][1]
    assert right_high[4][1] < right_high[2][1]
    bad = [8720,6685,4860,2410,3860,9000]
    try:
        l_polygon(bad)
    except ValueError as exc:
        assert "95 mm" in str(exc)
        assert bad[-1] == 9000
    else:
        raise AssertionError("Unclosed L accepted")
    assert door_dimensions(6,.35,.9) == (.35,.8,4.75,5.2)
    try:
        door_dimensions(1,.35,.9)
    except ValueError:
        pass
    else:
        raise AssertionError("Out-of-wall door accepted")
    pts = l_polygon(initial)
    # Square butt joints cover the same physical wall ring in either winding.
    for outline in ([(0,0),(4,0),(4,6),(0,6)], pts):
        for points in (outline, list(reversed(outline))):
            panels = [wall_polygon(points, i, .1)
                      for i,length in enumerate(wall_lengths(points))]
            for panel in panels:
                edges = np.roll(panel,-1,axis=0)-panel
                assert np.allclose(np.sum(edges*np.roll(edges,-1,axis=0),axis=1),0,atol=1e-8)
            room = Polygon(points)
            expected = room.buffer(.1,join_style=2).difference(room)
            actual = unary_union([Polygon(panel) for panel in panels])
            assert actual.symmetric_difference(expected).area < 1e-8
    doors = [("Fryserom enkel 900×2100 mm",1,0,.35)]
    info = dict(navn="L-form kontroll",pnr="",tnr="",dato="",maal="1:50",ttype="Plan",A=20,P=21)
    out = Path(__file__).parent / "qa"
    out.mkdir(exist_ok=True)
    for title, fig in (
        ("l-plan", stramo_plan(pts,2.5,1.1,doors,info)),
        ("l-door", tegn_veggoppstalt(pts,2.5,1.1,doors,info,rom_type="Fryserom")),
    ):
        labels = [text.get_text() for text in fig.axes[0].texts]
        assert "350 mm" in labels and "4750 mm" in labels
        if title == "l-plan":
            assert "Senter 800 mm" not in labels
        else:
            assert "Senter 800 mm" not in labels
        fig.savefig(out/f"{title}.png",dpi=110)
        plt.close(fig)
    print("PASS: 18 L orientations, unchanged inputs, square butt wall joints, closure, door bounds and plan/elevation dimensions")


if __name__ == "__main__":
    check()
