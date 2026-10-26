"""Approved exterior dimensions, purchase units, reusable floor cuts and PDF columns."""
import io
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from pypdf import PdfReader
from project_file import decode_project, world_input, form_points, encode_project, freezer_shared_walls
from construction import floor_outline, roof_outline, wall_polygon
from dimensions import inside_from_outside, exterior_door
from geometry import transform_polygon, wall_lengths
from database import PANEL_DB
from kalkulasjon import beregn_prosjekt
from finishing import plywood_cuts, board_count, pack_boards
from cutlist_pdf import project_materials, cutting_pdf, MATERIAL_COLUMNS
from purchase_summary import grouped_panels
from montasje import tegn_plantegning, tegn_snitt
import matplotlib.pyplot as plt
from fdv import lag_fdv_oversikt
for kind in ('Kjølerom','Fryserom'):
    overview=lag_fdv_oversikt('PIR 100 mm',kind,[],['Trykkventil / trykkutligningsplugg','Terskel / rampe rustfritt stål'])
    assert overview.Produkt.str.contains('Trykkventil').any() == (kind=='Fryserom')
    assert overview.Produkt.str.contains('Terskel').any() == (kind=='Fryserom')

project=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())
rooms=project['rooms']
assert {m[1] for m in freezer_shared_walls(rooms)} == {3,4}
for room, size in zip(rooms, ((8.96,8.91),(3.91,7.46))):
    inp=world_input(room); t=PANEL_DB[inp.panel_key]['t']/1000
    outside=np.asarray(floor_outline(inp.pts,t))
    assert np.allclose(np.ptp(outside,axis=0),size)
    assert np.allclose(roof_outline(inp.pts,t,inp.rom_type),outside)
    for turn in range(4):
        for mirror in (False,True):
            outer=transform_polygon(form_points(room['form']),turn,mirror)
            inner=inside_from_outside(outer,t)
            assert Polygon(inner).symmetric_difference(Polygon(outer).buffer(-t,join_style=2)).area<1e-8
            assert np.allclose(floor_outline(inner,t),outer)
    result=beregn_prosjekt(inp)
    m=result['df_mat']; panels=m[m.Type==PANEL_DB[inp.panel_key]['label']]
    assert panels.Enhet.eq('m²').all()
    assert panels['Enhetspris (kr)'].eq(900 if t==.08 else 1000).all()
    assert np.allclose(panels['Totalpris (kr)'], (panels.Mengde*panels['Enhetspris (kr)']).round(2))
    fig=tegn_plantegning(inp,result)
    texts=[text.get_text() for ax in fig.axes for text in ax.texts]
    assert not any('innvendig' in text.lower() or 'innv.' in text.lower() for text in texts)
    assert any('1000 × 2100 mm'==text for text in texts)
    for key,count,wall,offset,hinge in inp.dorer:
        start,length,external_offset=exterior_door(inp.pts,t,wall,offset)
        assert f'{external_offset*1000:.0f} mm' in texts
        assert f'{(length-external_offset-1)*1000:.0f} mm' in texts
    if t==.1:
        assert texts.count('3910 mm')==1 and texts.count('7460 mm')==1
        assert np.allclose(np.ptp(inp.pts,axis=0),(3.71,7.26))
    else:
        assert '6410 mm' in texts and np.isclose(wall_lengths(outside)[2],6.41)
    plt.close(fig)
    fig=tegn_snitt(inp,result)
    texts=[text.get_text() for ax in fig.axes for text in ax.texts]
    assert any('utvendig' in x for x in texts) and any('innvendig' in x for x in texts)
    plt.close(fig)

cuts=plywood_cuts(world_input(rooms[1]).pts)
assert len(cuts)==9 and board_count(cuts)==7
assert np.isclose(sum(r['Areal_m2'] for r in cuts),3.71*7.26)
floor=unary_union([Polygon(r['polygon']) for r in cuts])
assert floor.symmetric_difference(Polygon(world_input(rooms[1]).pts)).area<1e-8
assert abs(sum(Polygon(r['polygon']).area for r in cuts)-floor.area)<1e-8
for sheet in {r['Råplate'] for r in cuts}:
    parts=[box(r['KappX_mm'],r['KappY_mm'],r['KappX_mm']+r['Råbredde_mm'],r['KappY_mm']+r['Rålengde_mm']) for r in cuts if r['Råplate']==sheet]
    assert all(box(0,0,1500,3000).covers(p) for p in parts)
    for i,p in enumerate(parts):
        for q in parts[i+1:]: assert p.distance(q)>=3-1e-8
# A 200 mm residual width is NOT retained; a 201 mm residual is reusable.
for width,expected in ((297,2),(296,1)):
    sample=[dict(Plate='A',Bredde_mm=width,Lengde_mm=500),dict(Plate='B',Bredde_mm=200,Lengde_mm=500)]
    assert board_count(pack_boards(sample,500,500))==expected

group=grouped_panels(rooms)
assert group.Bestill_hele_elementer.sum()==75
assert np.isclose(group.Bestill_m2.sum(),274.593)
materials=project_materials(rooms)
assert materials.loc[materials.Produkt.str.startswith('Gulvplate'),'Stk'].sum()==7
assert MATERIAL_COLUMNS['Beslag']==['Produkt','Stk']
assert MATERIAL_COLUMNS['Dører']==MATERIAL_COLUMNS['Tilbehør']==['Produkt','Stk']
pdf=PdfReader(io.BytesIO(cutting_pdf(rooms,'materialer')))
assert len(pdf.pages)==2
assert 'Elementer' in pdf.pages[0].extract_text()
text=pdf.pages[1].extract_text()
assert 'Lengde\nLM' not in text and 'Areal' not in text
floor_pdf=PdfReader(io.BytesIO(cutting_pdf(rooms,'finer')))
text='\n'.join(p.extract_text() for p in floor_pdf.pages)
assert all(c not in text for c in ('X mm','Y mm','Merknad','gulvfiberplate','Én råplate per del'))
assert 'Råplate' in text and '3 mm sagspor' in text
encoded=encode_project(rooms,project['draft'],project['active_id'])
assert decode_project(encoded)['rooms']==rooms
print('PASS: all r08 dimensions, prices, exterior door chains, floor coverage, offcut nesting and PDF columns')
