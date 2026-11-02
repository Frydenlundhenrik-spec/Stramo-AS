"""Confirmed opening surround and freezer floor angle, from quantities to exports."""
from dataclasses import replace
from pathlib import Path
from copy import deepcopy
import io
import math
import numpy as np
from pypdf import PdfReader
from project_file import decode_project, world_input
from kalkulasjon import beregn_prosjekt
from finishing import TRIM_PROFILES, opening_trim_runs
from construction import fixing_screw_count, wall_base, finished_floor
from cutlist_pdf import project_materials, cutting_pdf
from beslag_profiles import profile_rows, profile_png
from drawing_3d import tegn_3d_med_panelbredde
from transport import packages

rooms = decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
freezer = replace(world_input(rooms[1]), pts=[(0,0),(1.8,0),(1.8,1.8),(0,1.8)],
                  hoyde_m=2.4, dorer=[], apninger=[], excluded_walls=(), shared_walls=())
result = beregn_prosjekt(freezer)
bb = result['beslag']
# A 2000 x 2000 mm room has 7200 mm of inside floor angle. It is NOT 50x50.
assert bb['lm_gulv_tot']==7.2 and bb['stk_gulv']==4
assert bb['lm_inn_tot']==16.75 and bb['stk_inn']==8
assert not any('gulv' in row['Kapp'] for row in bb['kapp_inn'])
assert all('gulv' in row['Kapp'] for row in bb['kapp_gulv'])
omitted = beregn_prosjekt(replace(freezer, excluded_walls=(0,)))['beslag']
assert math.isclose(omitted['lm_gulv_tot'],5.6)  # exposed ends extend to the unchanged outside footprint
assert math.isclose(wall_base('Fryserom', freezer.panel_key),.122)
assert math.isclose(finished_floor('Fryserom', freezer.panel_key),.134)
fig = tegn_3d_med_panelbredde(freezer.pts,2.4,[],freezer.panel_key,freezer.rom_type,1.1)
angle = next(trace for trace in fig.data if trace.name.startswith('Gulvvinkel fryserom'))
assert np.allclose([min(angle.z),max(angle.z)],[.134,.184])
assert math.isclose(min(angle.y),-.03)

# The profile drawing has a left-facing 30 mm flange with no return at its tip.
from unittest.mock import patch
import matplotlib.pyplot as plt
profile_png.cache_clear()
with patch('matplotlib.pyplot.close'):
    profile_png('floor',30)
    profile_figure = plt.gcf()
    ax = profile_figure.axes[0]
    outline = ax.lines[0].get_xydata()
    assert np.allclose(outline[-2:],[(0,0),(-30,0)])
    assert max(outline[:,0]) == 0
    assert sum(t.get_text()=='10 mm' for t in ax.texts) == 1
plt.close(profile_figure)

# 1000 x 1855 opening: two jambs, sill and header = 5710 mm, three 2500 mm bars.
opening = (0,.2,1.0,1.855,.2,'Glassfront')
cooler = replace(freezer, rom_type='Kjølerom',panel_key='PIR 80 mm',apninger=[opening])
result = beregn_prosjekt(cooler)
assert result['beslag']['lm_apning_tot']==5.71 and result['beslag']['stk_apning']==3
assert result['beslag']['stk_gulv']==0
assert len(opening_trim_runs([opening],.08))==4
assert not opening_trim_runs([opening],.1)
assert not opening_trim_runs([opening],.08,(0,))
assert not opening_trim_runs([(0,.2,1.,1.8,.2,'Other')],.08)
plain = fixing_screw_count(cooler.pts,2.4,'Kjølerom',.08)
# Jambs: 12 each; sill and header: 8 each; 40 additional screws.
assert result['accessory_needs']['skruer_eske']==plain+40
fig = tegn_3d_med_panelbredde(cooler.pts,2.4,[],cooler.panel_key,cooler.rom_type,1.1,apninger=[opening])
surround = next(trace for trace in fig.data if trace.name=='Åpningsbeslag 50×80×15 mm')
assert len(surround.x)==48  # four sides, three faces on each
assert np.allclose([min(surround.y),max(surround.y)],[-.08,0])

# Real Tasty rooms, including a removable 1855 mm opening in the test copy.
rooms = deepcopy(rooms)
rooms[0]['input']['apninger']=[(1,.3,1.0,1.855,.2,'Glassfront')]
for room in rooms:
    result=beregn_prosjekt(world_input(room))
    mat=project_materials([room])
    for product, post, key in TRIM_PROFILES:
        count=result['beslag'][f'stk_{key}']
        assert result['df_mat'].loc[result['df_mat'].Post.eq(post),'Mengde'].sum()==count
        assert mat.loc[mat.Produkt.str.startswith(product),'Stk'].sum()==count
        assert mat.loc[mat.Produkt.str.startswith(product),'Løpemeter'].sum()==2.5*count
profiles=profile_rows(project_materials(rooms))
assert {r['kind'] for r in profiles}=={'inner','outer','channel','floor','opening'}
assert next(r for r in profiles if r['kind']=='floor')['name']=='Gulvvinkel fryserom 30 × 50 mm'
for kind in ('beslagprofiler','materialer','alle','bestilling_tilbehor'):
    data=cutting_pdf(rooms,kind)
    text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)
    for value in ('30','50','80','15'):
        assert value in text
    assert 'Gulvvinkel fryserom' in text and 'Innvendig gulvbeslag' not in text
    Path(f'output/pdf/kontroll-nye-beslag-{kind}.pdf').write_bytes(data)
colli=packages(rooms)
assert colli.Innhold.str.contains('30×50').any()
assert colli.Innhold.str.contains('50×80×15').any()
print('PASS: 50/80/15 openings; 30/50 floor; 100 mm floor; screw counts; calculation/order/PDF/3D/transport parity')
