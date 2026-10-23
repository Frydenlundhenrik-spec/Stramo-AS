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
assert mat[mat.Produkt.str.startswith('Gulvfiberplate')].Stk.sum()==9
assert mat[mat.Gruppe=='Elementer'].Stk.sum()==77
assert abs(mat[mat.Gruppe=='Elementer'].Vekt_kg.sum()-3442.2806)<1e-6
(root/'Filkontroll.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'LES-MEG.txt').write_text('TASTY FREDRIKSTAD - OPPDATERTE KAPPLISTER OG MATERIALLISTER\n23.10.2026 – revisjon 07\n\n01-Kjolerom: kjølerom alene, med fellesvegger utelatt som i prosjektet.\n02-Fryserom: fryserom alene, med alle fryseromsvegger.\n03-Hele-prosjektet: begge rom samlet, like produkter summert.\n\nNye regler: panelvekt beregnes automatisk fra Balex-produktdata (80 mm 11,8 kg/m²; 100 mm 12,6 kg/m²). Kun beslag, inkludert U-kanaler, får 10 % svinn/kapp, avrundet opp til hele 2500 mm lengder per rom og profil. Paneler og gulvplater har ikke prosentvis kapptillegg. Gulvplater følger eksisterende kapplan, én råplate per del.\n\nProsjektsum: 77 panelelementer, 282,953 m² bestilt panelareal, 3442,281 kg panelvekt uten tilbehør/emballasje. 41 innvendige vinkler, 41 utvendige vinkler, 13 U-kanaler, totalt 237,5 løpemeter. 9 gulvplater, 1500 × 3000 × 12 mm.\n\nProsjektgrunnlag: Tasty-Rom4-og-fryserom-med-dorer.json. Mål, dører og fellesvegger er beholdt.\n',encoding='utf-8')
for start in range(0,len(thumbs),9):
    sheet=Image.new('RGB',(1260,3*325),'#d9dfe3');draw=ImageDraw.Draw(sheet)
    for j,(label,im) in enumerate(thumbs[start:start+9]):
        x=(j%3)*420;y=(j//3)*325
        sheet.paste(im,(x,y+22));draw.text((x+6,y+4),label,fill='black')
    sheet.save(review/f'contact-{start//9+1}.png')
print('PASS: 14 PDF files;',len(thumbs),'unique pages rendered; quantities verified')
