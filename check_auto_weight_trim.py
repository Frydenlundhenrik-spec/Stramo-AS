"""Regression: automatic weights, fixed trim allowance and no board allowance."""
from copy import deepcopy
from pathlib import Path
import math
import io
import pandas as pd
from pypdf import PdfReader
from project_file import decode_project,world_input
from purchase_summary import panel_summary,grouped_panels,grouped_cuts,estimated_panel_weight
from cutlist_pdf import project_materials,cutting_pdf
from kalkulasjon import beregn_prosjekt
from finishing import trim_order,plywood_cuts,board_count
from geometry import wall_lengths
from construction import wall_span
from database import PANEL_DB

rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
assert trim_order(10)==5 and trim_order(0)==0
assert trim_order(25/1.1)==10 and trim_order(25/1.1+.001)==11
assert [estimated_panel_weight(f'PIR {t} mm') for t in (80,100,120)]==[11.8,12.6,13.2]
summary=panel_summary(rooms)
assert set(summary.Vektgrunnlag)=={'Balex produktdatablad'}
assert all(abs(row.Bestill_vekt_kg-row.Bestill_m2*row.Kg_pr_m2)<1e-9 for row in summary.itertuples())
old=deepcopy(rooms)
for room in old:room['form'].update(waste_pct=99,panel_kg_m2=450)
pd.testing.assert_frame_equal(grouped_panels(rooms),grouped_panels(old))
pd.testing.assert_frame_equal(grouped_cuts(rooms),grouped_cuts(old))
pd.testing.assert_frame_equal(project_materials(rooms),project_materials(old))
for room in rooms:
    inp=world_input(room);result=beregn_prosjekt(inp);bb=result['beslag']
    mat=project_materials([room]);calc=result['df_mat']
    for label,key,post in [('Innvendig','kapp_inn','Innv.'),('Utvendig','kapp_ut','Utv.')]:
        net=sum(2500-r['Rest_mm'] for r in bb[key])/1000
        wanted=math.ceil(net*1.1/2.5-1e-10)
        row=mat[mat.Produkt.str.startswith(label)].iloc[0]
        assert row.Stk==wanted and row.Løpemeter==wanted*2.5
        assert calc[calc.Post.str.startswith(post)].Mengde.sum()==wanted
    if inp.rom_type=='Fryserom':
        f=room['form'];width,length=f.get('plywood_width_mm',1500),f.get('plywood_length_mm',3000)
        assert (width,length)==(1500,3000)
        qty=board_count(plywood_cuts(inp.pts,width,length))
        assert qty==7
        assert mat[mat.Produkt.str.startswith('Gulvplate')].Stk.sum()==qty
        assert mat[mat.Produkt.str.startswith('Gulvplate')].Areal_m2.sum()==31.5
        assert not mat.Produkt.str.startswith('U-kanal').any()
    else:
        spans=[wall_span(inp.pts,i,PANEL_DB[inp.panel_key]['t']/1000,inp.excluded_walls) for i in range(len(inp.pts)) if i not in inp.excluded_walls]
        net=sum(hi-lo for lo,hi in spans)
        assert mat[mat.Produkt.str.startswith('U-kanal')].Stk.sum()==math.ceil(net*1.1/2.5-1e-10)
for kind in ('materialer','beslag','finer','elementer','beslagprofiler'):
    data=cutting_pdf(old,kind)
    text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    assert '5 % tillegg' not in text and 'valgt tillegg' not in text
    assert 'like lengder samlet' not in text and 'Kapp per 2500 mm stang' not in text
    Path(f'output/pdf/kontroll-automatisk-{kind}.pdf').write_bytes(data)
print('PASS: automatic catalogue weights; old overrides ignored; trim 10% once + ceiling; boards/panels no allowance; calculation and PDFs agree')
print(project_materials(rooms)[['Produkt','Stk','Areal_m2','Vekt_kg','Løpemeter']].to_string(index=False))
