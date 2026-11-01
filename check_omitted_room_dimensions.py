"""2 x 2 m remains 2 x 2 m after wall removal, across fabrication and exports."""
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
from itertools import combinations
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import ifcopenshell
import ifcopenshell.geom
from shapely.geometry import Polygon, MultiPoint
from shapely.ops import unary_union
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from construction import floor_outline, wall_polygon, wall_panel_layout, wall_span
from dimensions import inside_from_outside, exterior_wall, exterior_door
from geometry import transform_polygon, l_polygon
from kalkulasjon import ProjectInput, beregn_prosjekt
from montasje import tegn_plantegning, tegn_taktegning, tegn_3d_modell, figur_som_pdf
from ifc_export import gen_ifc
from project_file import make_room, encode_project, decode_project, world_input, sync_shared_walls, snap_room
from purchase_summary import grouped_panels

def room(t=.08, omitted=()):
    pts = inside_from_outside([(0,0),(2,0),(2,2),(0,2)], t)
    return ProjectInput('Kontroll 2000 x 2000', '138', 'A101', '01.11.2026', 'Ikke målfast',
                        'Fryserom' if t == .1 else 'Kjølerom', f'PIR {round(t*1000)} mm',
                        pts, 2.4, 1.1, [], [], excluded_walls=omitted)

shapes = [[(0,0),(2,0),(2,2),(0,2)],
          l_polygon([6000,2500,3500,2000,2500,4500]),
          [(0,0),(5,0),(5,3),(3,5),(0,5)]]
for t in (.08,.1):
    for outside in shapes:
        for turn in range(4):
            for mirror in (False,True):
                pts = inside_from_outside(transform_polygon(outside,turn,mirror), t)
                outline = Polygon(floor_outline(pts,t))
                for count in (1,2):
                    for omitted in combinations(range(len(pts)),count):
                        walls = []
                        layout = wall_panel_layout(pts,1100,t,omitted)
                        for i in range(len(pts)):
                            if i in omitted: continue
                            wall = Polygon(wall_polygon(pts,i,t,omitted))
                            assert wall.is_valid and wall.area > 0
                            assert wall.difference(outline).area < 1e-8
                            walls.append(wall)
                            assert np.allclose(exterior_wall(pts,t,i,omitted), exterior_wall(pts,t,i))
                            lo,hi=wall_span(pts,i,t,omitted)
                            assert sum(p['width_mm'] for p in layout if p['wall']==i)==round(hi*1000)-round(lo*1000)
                        assert sum(w.area for w in walls)-unary_union(walls).area < 1e-8

settings=ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)
for t in (.08,.1):
    for removed in range(4):
        inp=room(t,(removed,)); result=beregn_prosjekt(inp)
        baseline=beregn_prosjekt(room(t))
        # Three outside trim runs remain 2000 mm. The two free inner ends
        # gain one panel thickness each, with no fictitious fourth-wall trim.
        assert result['beslag']['lm_ut_tak'] == 6
        assert np.isclose(result['beslag']['lm_inn_tak'],6-4*t)
        for zone in ('Tak','Gulv'):
            assert result['df_kapp'].query('Vegg == @zone').reset_index(drop=True).equals(
                baseline['df_kapp'].query('Vegg == @zone').reset_index(drop=True))
        walls=[Polygon(wall_polygon(inp.pts,i,t,inp.excluded_walls)) for i in range(4) if i!=removed]
        assert np.allclose(unary_union(walls).bounds,(0,0,2,2))
        for i in range(4):
            assert np.isclose(np.linalg.norm(np.subtract(*exterior_wall(inp.pts,t,i,inp.excluded_walls))),2)
            _,length,offset=exterior_door(inp.pts,t,i,.22-t,inp.excluded_walls)
            assert np.isclose(length,2) and np.isclose(offset,.22)
        cuts=result['df_kapp'].query('Vegg.str.startswith("Vegg")',engine='python')
        assert np.isclose(cuts.Areal_m2.sum(),sum(w.area/t*inp.hoyde_m for w in walls),atol=.003)
        figure=tegn_3d_modell(inp)
        actual=[MultiPoint(np.column_stack([tr.x,tr.y])).convex_hull for tr in figure.data
                if (tr.name or '').startswith('Vegg ') and '– panel' in tr.name]
        assert unary_union(actual).symmetric_difference(unary_union(walls)).area < 1e-8
        model=ifcopenshell.file.from_string(gen_ifc(inp.pts,inp.hoyde_m,inp.navn,inp.panel_key,
            inp.dorer,inp.rom_type,inp.panelbredde_m,excluded_walls=inp.excluded_walls).decode())
        actual=[]
        for wall in model.by_type('IfcWall'):
            mesh=ifcopenshell.geom.create_shape(settings,wall)
            vertices=np.array(mesh.geometry.verts).reshape(-1,3)
            actual.append(MultiPoint(vertices[:,:2]).convex_hull)
        assert unary_union(actual).symmetric_difference(unary_union(walls)).area < 1e-8

inp=room(.08,(3,)); result=beregn_prosjekt(inp)
for draw in (tegn_plantegning,tegn_taktegning):
    fig=draw(inp,result)
    text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(figur_som_pdf(fig))).pages)
    assert '2000 mm' in text and '1920 mm' not in text and '2080 mm' not in text
    fig.savefig(Path('qa')/(draw.__name__+'-2000.png'),dpi=110)
    plt.close(fig)

form=dict(kind='Rektangel',length_mm=2000,width_mm=2000,dimension_basis='external')
opened=make_room(room(),form,{})
opened['excluded_walls']=[3]
target=make_room(room(),form,{})
opened['position_mm']=snap_room(opened,3,target,1)
project=decode_project(encode_project([target,opened],opened,opened['id']))
assert project['rooms'][1]['input']['shared_walls']==[3]
assert world_input(project['rooms'][1]).shared_walls==[3]
before=grouped_panels(project['rooms'])
assert before.equals(grouped_panels(decode_project(encode_project(project['rooms'],project['draft'],project['active_id']))['rooms']))
project['rooms'][1]['position_mm']=[10000,0]
sync_shared_walls(project['rooms'])
assert project['rooms'][1]['input']['shared_walls']==[]  # Stale contact is cleared after moving away.

# Exercise the actual editor: removing and restoring a wall cannot modify its dimensions.
app=AppTest.from_file('app.py',default_timeout=90).run()
single=decode_project(encode_project([opened],opened,opened['id']))
app.session_state['pending_project']=single
app.run()
app.radio(key='ed_module').set_value('Tegninger').run()
assert not app.exception
for omitted in ([3],[],[0],[1],[2],[3]):
    app.multiselect(key='ed_drawing_walls').set_value(omitted).run()
    assert not app.exception
    saved=app.session_state['last_valid_editor']
    assert saved['form']['length_mm']==2000 and saved['form']['width_mm']==2000
    assert np.allclose(floor_outline(saved['input']['pts'],.08),[(0,0),(2,0),(2,2),(0,2)])
print('PASS: omitted walls preserve exterior dimensions, free end geometry, 2D/PDF, roof/floor, 3D/IFC, quantities, shared contacts and editor save/reload')
