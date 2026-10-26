"""Visual-review regressions: concave meshes, square ends and honest cut labels."""
from pathlib import Path
import re
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
from construction import roof_outline, wall_span
from database import PANEL_DB
from drawing_2d import wall_panel_polygon, _panel_to_local, _edge_kind, _draw_one_panel
from drawing_3d import _polygon_triangles, tegn_3d_med_panelbredde
from geometry import l_polygon, wall_lengths
from panel_engine import generate_roof_floor_panels
from project_file import decode_project, world_input


def check_triangles(points):
    points = np.asarray(points, dtype=float)
    triangles = [Polygon(points[list(indices)]) for indices in _polygon_triangles(points)]
    union = unary_union(triangles)
    assert union.symmetric_difference(Polygon(points)).area < 1e-8
    assert abs(sum(triangle.area for triangle in triangles)-union.area) < 1e-8


l_shape = l_polygon([6000,2500,3500,2000,2500,4500])
u_shape = [(0,0),(5,0),(5,4),(4,4),(4,1),(1,1),(1,4),(0,4)]
pentagon = [(0,0),(5,0),(5,3),(3,5),(0,5)]
collinear = [(0,0),(2,0),(4,0),(4,4),(0,4)]
for outline in (l_shape,u_shape,pentagon,collinear):
    for points in (outline,list(reversed(outline))):
        check_triangles(points)
        for index,length in enumerate(wall_lengths(points)):
            lo,hi = wall_span(points,index,.1)
            panel = wall_panel_polygon(points,index,lo,hi,.1)
            edges = np.roll(panel,-1,axis=0)-panel
            if outline is not pentagon:
                assert np.allclose(np.sum(edges*np.roll(edges,-1,axis=0),axis=1),0,atol=1e-8)
            assert Polygon(panel).is_valid
            omitted = ((index-1)%len(points),(index+1)%len(points))
            open_panel = wall_panel_polygon(points,index,0,length,.1,excluded_walls=omitted)
            assert np.allclose(open_panel[:2],np.asarray(points)[[index,(index+1)%len(points)]])

rooms = decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
for room in rooms:
    inp = world_input(room)
    outline_points = roof_outline(inp.pts,PANEL_DB[inp.panel_key]['t']/1000,inp.rom_type)
    outline = Polygon(outline_points)
    fig = tegn_3d_med_panelbredde(inp.pts,inp.hoyde_m,inp.dorer,inp.panel_key,inp.rom_type,
                                 inp.panelbredde_m,excluded_walls=inp.excluded_walls)
    roof_triangles = []
    for trace in fig.data:
        if trace.type == 'mesh3d' and re.match(r'T\d+ ',trace.name or '') and 'tykkelse' not in trace.name:
            points = np.column_stack([trace.x,trace.y])
            roof_triangles.extend(Polygon(points[[a,b,c]]) for a,b,c in zip(trace.i,trace.j,trace.k))
            assert 0 < trace.opacity < .5 and trace.color == '#aab1b7'
        if trace.name == 'Takskravering':
            for index in range(0,len(trace.x),3):
                segment = LineString([(trace.x[index],trace.y[index]),(trace.x[index+1],trace.y[index+1])])
                assert segment.difference(outline.buffer(1e-9)).length < 1e-8
    roof = unary_union(roof_triangles)
    assert roof.symmetric_difference(outline).area < 1e-8
    assert abs(sum(triangle.area for triangle in roof_triangles)-roof.area) < 1e-8
    for panel in generate_roof_floor_panels(outline_points,1100,prefix='T'):
        if len(panel.polygon) <= 4:
            continue
        local = _panel_to_local(panel.polygon)
        assert all(_edge_kind(local,panel.width_mm,i) != 'vinklet kapp' for i in range(len(local)))
        detail,ax = plt.subplots()
        _draw_one_panel(ax,local,panel,inp.panel_key,1)
        labels = [text.get_text() for text in ax.texts]
        assert not any('°' in label for label in labels)
        assert not any(label in ('F','RK','VK') for label in labels)
        assert not any('Snittvinkel' in label for label in labels)
        plt.close(detail)
print('PASS: concave roof coverage, nonoverlapping triangles, clipped gray hatch, square wall ends, omitted neighbors and T3 cut/angle labels')
