"""Check that the special vertical profiles in the 3D view fit the two wall faces."""
import numpy as np

from construction import floor_outline, finished_floor, wall_base
from drawing_3d import tegn_3d_med_panelbredde
from geometry import transform_polygon


def check_view(points, room_type, thickness, excluded=()):
    panel = f"PIR {thickness} mm"
    fig = tegn_3d_med_panelbredde(points, 2.4, [], panel, room_type, 1.1,
                                  excluded_walls=excluded)
    profiles = [t for t in fig.data if "skråbeslag 100×100 mm" in t.name]
    indexes = [] if 2 in excluded else [2, 3]
    assert len(profiles) == 2 * len(indexes)
    outer = floor_outline(points, thickness / 1000)
    for i in indexes:
        for inner in (True, False):
            side = "Innvendig" if inner else "Utvendig"
            trace, = (t for t in profiles if t.name.startswith(side)
                      and t.name.endswith(f"H{i+1}"))
            finished, bend = {2: (116, 64), 3: (153, 27)}[i]
            assert f"ferdig vinkel {finished}° · knekk fra flat plate {bend}°" in trace.name
            vertex = np.array((points if inner else outer)[i])
            xyz = np.column_stack((trace.x, trace.y, trace.z))
            assert xyz.shape == (24, 3)
            for start, j in ((0, i-1), (12, (i+1) % len(points))):
                direction = np.subtract(points[j], points[i])
                direction /= np.linalg.norm(direction)
                assert np.allclose(xyz[start, :2], vertex)
                assert np.allclose(xyz[start+1, :2], vertex + .100 * direction)
                assert np.allclose(xyz[start+9, :2] - xyz[start+8, :2], -.010 * direction)
            bottom = finished_floor(room_type, panel) if inner else wall_base(room_type, panel)
            assert np.isclose(min(trace.z), bottom)
            assert np.isclose(max(trace.z), wall_base(room_type, panel) + 2.4)


points = [(0., 0.), (5., 0.), (5., 3.), (3., 4.), (0., 4.)]
check_view(points, "Kjølerom", 80)
check_view(transform_polygon(points, 1, True), "Fryserom", 100)
check_view(points, "Kjølerom", 80, (2,))
print("PASS: two real 100 mm flanges, 10 mm returns, exterior vertices, omitted walls and freezer floor levels")
