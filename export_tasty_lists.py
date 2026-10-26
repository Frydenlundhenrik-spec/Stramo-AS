"""Refresh Tasty lists using the application's current calculation/export path."""
from pathlib import Path
import hashlib
import json
import sys
from pypdf import PdfReader
import pypdfium2 as pdfium
from PIL import Image,ImageDraw
from project_file import decode_project
from cutlist_pdf import cutting_pdf,project_materials
from purchase_summary import grouped_panels

root=Path(sys.argv[1] if len(sys.argv)>1 else 'output/Kapplister-og-materiallister-2026-10-22')
root.mkdir(parents=True,exist_ok=True)
project=Path('Tasty-Rom4-og-fryserom-med-dorer.json')
rooms=decode_project(project.read_bytes())['rooms']
kinds={'materialer':'01-Materialliste.pdf','alle':'02-Alle-kapplister.pdf',
       'elementer':'03-Elementkapplister.pdf',
       'beslagprofiler':'05-Beslagsliste-med-profiler.pdf','finer':'06-Gulvplatekappliste.pdf'}
scopes=[('01-Kjolerom',rooms[:1]),('02-Fryserom',rooms[1:]),('03-Hele-prosjektet',rooms)]
manifest=[]
review=Path('tmp/pdfs/tasty-updated-lists');review.mkdir(parents=True,exist_ok=True)
thumbs=[]
for folder,selected in scopes:
    dest=root/folder;dest.mkdir(exist_ok=True)
    material=project_materials(selected)
    for kind,name in kinds.items():
        if kind=='finer' and folder=='01-Kjolerom':continue
        path=dest/name;data=cutting_pdf(selected,kind);path.write_bytes(data)
        doc=PdfReader(path)
        text='\n'.join(p.extract_text() for p in doc.pages)
        assert '5 % tillegg' not in text and 'valgt tillegg' not in text
        assert all(len(p.extract_text().strip())>100 for p in doc.pages),path
        manifest.append(dict(file=str(path.relative_to(root)),pages=len(doc.pages),sha256=hashlib.sha256(data).hexdigest()))
        # All unique PDF layouts appear in the combined cutting and material files.
        if kind in ('alle','materialer'):
            rendered=pdfium.PdfDocument(path)
            for i in range(len(rendered)):
                im=rendered[i].render(scale=1.2).to_pil()
                im.save(review/f'{folder}-{kind}-{i+1}.png')
                im.thumbnail((420,300))
                thumbs.append((f'{folder} {kind} p{i+1}',im))
    print(folder,'panels',int(grouped_panels(selected).Bestill_hele_elementer.sum()),
          'panel kg',round(float(grouped_panels(selected).Bestill_vekt_kg.sum()),3),flush=True)
assert len(manifest)==14
mat=project_materials(rooms)
assert mat[mat.Produkt.str.startswith('U-kanal')].Stk.sum()==13
assert mat[mat.Produkt.str.startswith('Gulvplate')].Stk.sum()==7
assert mat[mat.Gruppe=='Elementer'].Stk.sum()==75
assert abs(mat[mat.Gruppe=='Elementer'].Areal_m2.sum()-274.593)<1e-6
(root/'Filkontroll.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
mat.to_csv(root/'Materialgrunnlag.csv',index=False,encoding='utf-8-sig')
panels=mat[mat.Gruppe=='Elementer']
(root/'LES-MEG.txt').write_text(
    'TASTY FREDRIKSTAD – revisjon 09, 26.10.2026\n'
    'Kjølerom, fryserom og hele prosjektet har egne mapper.\n'
    f'Elementer: {int(panels.Stk.sum())} stk; {panels.Areal_m2.sum():.3f} m²; {panels.Vekt_kg.sum():.3f} kg panelvekt.\n'
    'Beslag: 13 U-kanaler, 40 innvendige og 41 utvendige vinkler. 2500 mm per lengde.\n'
    'Kun beslag får 10 % svinn før avrunding opp til hele lengder.\n'
    'Gulvplater: 7 råplater 1500 × 3000 × 12 mm til 9 deler. Råplatenummer i kapplisten viser gjenbruk.\n'
    'Avkapp brukes bare når begge restmål er over 200 mm og delen passer. Sagspor 3 mm.\n'
    'Paneler bestilles i hele elementbredder på oppgitt lengde, uten prosentvis kapp.\n'
    'Manglende manuelle tilbehørsmengder vises med strek og må fylles ut før komplett bestilling.\n',encoding='utf-8')
for start in range(0,len(thumbs),9):
    sheet=Image.new('RGB',(1260,3*325),'#d9dfe3');draw=ImageDraw.Draw(sheet)
    for j,(label,im) in enumerate(thumbs[start:start+9]):
        x=(j%3)*420;y=(j//3)*325
        sheet.paste(im,(x,y+22));draw.text((x+6,y+4),label,fill='black')
    sheet.save(review/f'contact-{start//9+1}.png')
print('PASS: 14 PDF files;',len(thumbs),'unique pages rendered; quantities verified')
