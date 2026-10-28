from pathlib import Path
from copy import deepcopy
from io import BytesIO
from pypdf import PdfReader
import pypdfium2 as pdfium
from project_file import decode_project
from cutlist_pdf import project_materials,cutting_pdf
from purchase_summary import grouped_panels
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
f=project_materials(rooms);p=f[f.Gruppe=='Elementer'];g=grouped_panels(rooms)
assert not p.duplicated(['Produkt','Høyde_mm','Bredde_mm','Tykkelse_mm']).any()
assert p.Stk.sum()==70
assert abs(p.Areal_m2.sum()-g.Bestill_m2.sum())<1e-8
assert abs(p.Vekt_kg.sum()-g.Bestill_vekt_kg.sum())<1e-8
assert f.query("Gruppe=='Tilbehør' and Produkt=='22 mm hvite skruer'").Stk.sum()==3
assert project_materials(rooms[:1]).query("Gruppe=='Tilbehør' and Produkt=='22 mm hvite skruer'").Stk.sum()==2
assert project_materials(rooms[1:]).query("Gruppe=='Tilbehør' and Produkt=='22 mm hvite skruer'").Stk.sum()==2
clone=deepcopy(rooms);clone[0]['input']['hoyde_m']=2.401
assert project_materials(clone[:1]).query("Gruppe=='Tilbehør' and Produkt=='22 mm hvite skruer'").Stk.sum()==2
assert f[f.Gruppe=='Beslag'].Areal_m2.isna().all()
assert project_materials(rooms+deepcopy(rooms)).query("Gruppe=='Tilbehør' and Produkt=='22 mm hvite skruer'").Stk.sum()==6
out=Path('output/pdf');out.mkdir(parents=True,exist_ok=True)
f.to_csv(out/'materialliste-prosjekt.csv',index=False,encoding='utf-8-sig')
data=cutting_pdf(rooms,'materialer');(out/'materialliste-prosjekt.pdf').write_bytes(data)
r=PdfReader(BytesIO(data));assert 'eske à 500' in '\n'.join(p.extract_text() for p in r.pages)
doc=pdfium.PdfDocument(data)
for i in range(len(doc)):doc[i].render(scale=1.25).to_pil().save(f'tmp/pdfs/materialer-new-{i+1}.png')
print(f.to_string(index=False));print('PASS: grouped material quantities, allowance, shared-wall screws, 400 mm ceiling and PDF',len(r.pages),'pages')
