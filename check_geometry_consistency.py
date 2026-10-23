"""Cross-format regression: actual solid footprints, panel cuts and project import."""
import copy
import json
from pathlib import Path
import numpy as np
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
from shapely.geometry import Polygon, MultiPoint
from shapely.ops import unary_union
from construction import wall_polygon, wall_span, wall_panel_layout, wall_panel_polygon, wall_outer_face_span
from geometry import l_polygon, transform_polygon
from database import PANEL_DB, DOR_DB
from project_file import decode_project, encode_project, world_input, freezer_shared_walls
from kalkulasjon import beregn_prosjekt
from ifc_export import gen_ifc
from montasje import tegn_3d_modell


def check():
    shapes=[[(0,0),(3.91,0),(3.91,7.46),(0,7.46)],
            l_polygon([8960,8910,6550,5050,2410,3860]),
            [(0,0),(5,0),(5,4),(4,4),(4,1),(1,1),(1,4),(0,4)],
            [(0,0),(5,0),(5,3),(3,5),(0,5)]]
    for original in shapes:
        for mirrored in (False,True):
            for turns in range(4):
                pts=transform_polygon(original,turns,mirrored)
                clear=Polygon(pts)
                for thickness in (.08,.1):
                    walls=[Polygon(wall_polygon(pts,i,thickness)) for i in range(len(pts))]
                    union=unary_union(walls)
                    assert union.intersection(clear).area<1e-8
                    assert abs(sum(w.area for w in walls)-union.area)<1e-8
                    expected=clear.buffer(thickness,join_style=2).difference(clear)
                    assert union.symmetric_difference(expected).area<1e-8
                    layout=wall_panel_layout(pts,1100,thickness)
                    slices=[Polygon(wall_panel_polygon(pts,p['wall'],p['start_mm']/1000,
                            (p['start_mm']+p['width_mm'])/1000,thickness)) for p in layout]
                    # Oblique corner projections can round by half a millimetre.
                    assert unary_union(slices).symmetric_difference(union).area<.001
    print('PASS: rectangles, L, U, oblique corners, all rotations/mirrors, both thicknesses; no interior wall area/gaps/overlaps')

    project=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())
    assert {match[1] for match in freezer_shared_walls(project['rooms'])}=={3,4}
    assert np.allclose(wall_outer_face_span(shapes[0],0,.1),(-.1,4.01))
    assert np.allclose(wall_outer_face_span(shapes[0],0,.1,[1]),(-.1,3.91))
    assert np.allclose(wall_outer_face_span(shapes[0],0,.1,[1,3]),(0,3.91))
    settings=ifcopenshell.geom.settings();settings.set(settings.USE_WORLD_COORDS,True)
    all_walls=[]
    summary=[]
    for room in project['rooms']:
        inp=world_input(room);thickness=PANEL_DB[inp.panel_key]['t']/1000
        result=beregn_prosjekt(inp)
        layout=wall_panel_layout(inp.pts,1100,thickness,inp.excluded_walls)
        cuts=result['df_kapp'].drop_duplicates('Elementnavn')
        for panel in layout:
            row=cuts[cuts.Elementnavn==panel['name']].iloc[0]
            assert int(row.Bredde_mm)==panel['width_mm']
        for i in range(len(inp.pts)):
            if i not in inp.excluded_walls:
                lo,hi=wall_span(inp.pts,i,thickness,inp.excluded_walls)
                assert sum(p['width_mm'] for p in layout if p['wall']==i)==round((hi-lo)*1000)
        model=ifcopenshell.file.from_string(gen_ifc(inp.pts,inp.hoyde_m,inp.navn,inp.panel_key,
            inp.dorer,inp.rom_type,inp.panelbredde_m,excluded_walls=inp.excluded_walls).decode())
        assert len(model.by_type('IfcDoor'))==2
        def opening_area(index):
            return sum(DOR_DB[d[0]]['bw']*DOR_DB[d[0]]['bh']/1e6*d[1]
                       for d in inp.dorer if d[2]==index)
        for wall in model.by_type('IfcWall'):
            index=int(wall.Name.split()[-1])-1
            shape=ifcopenshell.geom.create_shape(settings,wall)
            vertices=np.array(shape.geometry.verts).reshape(-1,3)
            footprint=MultiPoint(vertices[:,:2]).convex_hull
            expected=Polygon(wall_polygon(inp.pts,index,thickness,inp.excluded_walls))
            assert footprint.symmetric_difference(expected).area<1e-8
            assert np.isclose(ifcopenshell.util.shape.get_volume(shape.geometry),
                              expected.area*inp.hoyde_m-opening_area(index)*thickness)
            all_walls.append(footprint)
        figure=tegn_3d_modell(inp)
        for trace in figure.data:
            if trace.name.startswith('Vegg ') and '– panel' in trace.name:
                i=int(trace.name.split()[1])-1
                actual=MultiPoint(np.column_stack([trace.x,trace.y])).convex_hull
                assert actual.symmetric_difference(Polygon(wall_polygon(inp.pts,i,thickness,inp.excluded_walls))).area<1e-8
                direction=np.asarray(inp.pts[(i+1)%len(inp.pts)])-inp.pts[i]
                direction/=np.linalg.norm(direction)
                projected=np.column_stack([np.column_stack([trace.x,trace.y])@direction,trace.z])
                triangles=projected[np.column_stack([trace.i,trace.j,trace.k])]
                a=triangles[:,1]-triangles[:,0];b=triangles[:,2]-triangles[:,0]
                area=np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0]).sum()/2
                lo,hi=wall_span(inp.pts,i,thickness,inp.excluded_walls)
                assert np.isclose(area,2*((hi-lo)*inp.hoyde_m-opening_area(i)))
        summary.append({'room':inp.navn,'wall_panels':len(layout),'physical_wall_lengths_mm':[
            round((wall_span(inp.pts,i,thickness,inp.excluded_walls)[1]-wall_span(inp.pts,i,thickness,inp.excluded_walls)[0])*1000)
            for i in range(len(inp.pts)) if i not in inp.excluded_walls]})
    assert abs(sum(w.area for w in all_walls)-unary_union(all_walls).area)<1e-8
    print('PASS: Tasty plan/3D/IFC footprints identical, zero cross-room wall overlaps, four door openings cut through actual meshes/IFC, cut widths agree')
    bad=copy.deepcopy(project);bad['draft']=copy.deepcopy(bad['rooms'][1]);bad['active_id']=bad['rooms'][0]['id']
    for validate in (lambda:decode_project(json.dumps(bad).encode()),lambda:encode_project(bad['rooms'],bad['draft'],bad['active_id'])):
        try:validate()
        except ValueError:pass
        else:raise AssertionError('Mismatched active room accepted')
    print('PASS: mismatched room/draft rejected by save and import')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':check()
