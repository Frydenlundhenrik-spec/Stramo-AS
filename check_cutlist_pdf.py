from pathlib import Path
from io import BytesIO
from pypdf import PdfReader
import pypdfium2 as pdfium
from project_file import decode_project,world_input
from cutlist_pdf import cutting_pdf,project_materials
from kalkulasjon import beregn_prosjekt
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
out=Path('output/pdf');out.mkdir(parents=True,exist_ok=True)
tmp=Path('tmp/pdfs');tmp.mkdir(parents=True,exist_ok=True)
f=project_materials(rooms)
assert not f.duplicated(['Produkt','Høyde_mm','Bredde_mm','Tykkelse_mm']).any()
assert f[f.Gruppe=='Elementer'].Stk.sum()==77
assert f[f.Produkt.str.contains('50×50')].shape[0]==1
assert f[f.Produkt.str.contains('1000')].Stk.sum()==4
f.to_csv(out/'materialliste-prosjekt.csv',index=False,encoding='utf-8-sig')
for kind in ('alle','elementer','beslag','finer','materialer'):
    data=cutting_pdf(rooms,kind)
    path=out/('materialliste-prosjekt.pdf' if kind=='materialer' else f'kapplister-{kind}.pdf')
    path.write_bytes(data)
    reader=PdfReader(BytesIO(data));text='\n'.join(p.extract_text() for p in reader.pages)
    assert ('TOTAL BESTILLING' if kind=='beslag' else 'SUM') in text and len(text)>300
    assert 'like lengder samlet' not in text
    if kind=='beslag':assert len(reader.pages)==1
    if kind=='finer':
        assert len(reader.pages)==1
        assert 'Gulvplater – totalsummer' in text and '40,5' in text
    if kind=='materialer':
        assert len(reader.pages)==2
        elements,accessories=[p.extract_text() for p in reader.pages]
        assert 'Vekt' not in elements and 'BESTILLING /' not in elements
        assert 'SUM' not in accessories and 'Side 2' in accessories
        assert all(label in accessories for label in ('Materialliste','Beslag','Dører','Tilbehør','22 mm hvite skruer'))
        assert 'Produkt' not in accessories and 'Øvrige materialer' not in accessories
    for page_number,page in enumerate(reader.pages,1):
        assert 'Stramo AS' in page.extract_text() and f'Side {page_number}' in page.extract_text()
    doc=pdfium.PdfDocument(data)
    for i in range(len(doc)):
        doc[i].render(scale=1).to_pil().save(tmp/f'{kind}-{i+1}.png')
    print(kind,len(reader.pages),'pages')
assert len(PdfReader(BytesIO(cutting_pdf(rooms[:1],'finer'))).pages)==1
assert project_materials(rooms+rooms).Stk.sum()==2*f.Stk.sum()
print('PASS: PDFs, grouped totals, dimensions, shared-wall exclusions, doors and duplicate-room aggregation')
