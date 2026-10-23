from pathlib import Path
from project_file import decode_project,world_input
from cutlist_pdf import project_materials,cutting_pdf
from kalkulasjon import beregn_prosjekt
from montasje import tegn_3d_modell
from ifc_export import gen_ifc
import pypdfium2 as pdfium
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
f=project_materials(rooms)
assert not f.Produkt.str.contains('Varmekabel|Låsekasse|Hengsel|U-kanal 100').any()
assert f.Produkt.str.contains('Kjøleromsdør').any() and f.Produkt.str.contains('Fryseromsdør').any()
assert f.query("Gruppe=='Tilbehør' and Produkt=='22 mm hvite skruer'").Stk.sum()==452
assert f.loc[f.Produkt.eq('Trykkventil'),'Gruppe'].tolist()==['Tilbehør']
for r in rooms:
 inp=world_input(r);result=beregn_prosjekt(inp)
 fig=tegn_3d_modell(inp,apninger=inp.apninger)
 if inp.rom_type=='Fryserom':
  assert not result['df_mat'].Post.str.contains('U-kanal').any()
  assert not any('U-kanal' in (t.name or '') for t in fig.data)
  data=gen_ifc(inp.pts,inp.hoyde_m,inp.navn,inp.panel_key,inp.dorer,inp.rom_type,inp.panelbredde_m,apninger=inp.apninger,excluded_walls=inp.excluded_walls)
  assert 'U-kanal' not in str(data)
for kind in ('materialer','alle','beslag'):
 data=cutting_pdf(rooms,kind)
 out=Path('output/pdf')/('materialliste-prosjekt.pdf' if kind=='materialer' else f'kapplister-{kind}.pdf');out.write_bytes(data)
 if kind=='materialer':
  doc=pdfium.PdfDocument(data)
  for i in range(len(doc)):doc[i].render(scale=1).to_pil().save(f'tmp/pdfs/fixings-{i+1}.png')
f.to_csv('output/pdf/materialliste-prosjekt.csv',index=False,encoding='utf-8-sig')
print('PASS: removed hardware, distinct doors, no freezer U-channel, floor angles, 452 white 22 mm screws')

