"""Run with python check_beslag_profiles.py; also renders the three delivery PDFs."""
import io
from pathlib import Path
from pypdf import PdfReader
import pypdfium2 as pdfium
from project_file import decode_project, world_input
from kalkulasjon import beregn_prosjekt
from cutlist_pdf import cutting_pdf, project_materials
from beslag_profiles import profile_rows,profile_png
from transport import packages
from unittest.mock import patch
from matplotlib.axes import Axes
from PIL import Image

# Dimension labels are embedded in the profile raster, not repeated as PDF prose.
original_text,original_annotate=Axes.text,Axes.annotate
for kind,width in (('inner',50),('outer',150),('channel',80),('channel',100),('channel',120),('channel',150),('floor',30),('opening',80)):
    labels=[];annotations=[];side_labels=[]
    def record_text(self,x,y,label,*args,**kwargs):
        labels.append(str(label))
        artist = original_text(self,x,y,label,*args,**kwargs)
        if kind == 'channel' and label == '50 mm':
            side_labels.append(artist)
        return artist
    def record_annotation(self,label,*args,**kwargs):
        annotations.append(str(label))
        return original_annotate(self,label,*args,**kwargs)
    profile_png.cache_clear()
    with patch.object(Axes,'text',record_text),patch.object(Axes,'annotate',record_annotation):
        png=profile_png(kind,width)
    assert labels.count('10 mm')==(1 if kind in ('opening','floor') else 2) and not any('omknekk' in label for label in labels) and not any('10 mm' in label for label in annotations)
    assert f'{width} mm' in labels and '50 mm' in labels
    assert Image.open(io.BytesIO(png)).size==(960,500)
    if kind == 'channel':
        left, right = sorted(side_labels, key=lambda a: a.get_position()[0])
        ax = left.axes
        # The label boxes retain the PNG render coordinates after savefig.
        ax.figure.set_dpi(200)
        left_box = left.get_bbox_patch().get_window_extent()
        right_box = right.get_bbox_patch().get_window_extent()
        x0, x1 = ax.transData.transform([(0, 25), (width, 25)])[:, 0]
        assert 0 < left_box.x0 < left_box.x1 < x0 - 2
        assert x1 + 2 < right_box.x0 < right_box.x1 < ax.figure.bbox.x1

rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
combined=profile_rows(project_materials(rooms))
assert {r['kind'] for r in combined}=={'inner','outer','floor','channel'}
assert sum(r['qty'] for r in combined)==94 and sum(r['lm'] for r in combined)==235
for name,selection in [('prosjekt',rooms),('kjolerom',rooms[:1]),('fryserom',rooms[1:])]:
    rows=profile_rows(project_materials(selection))
    assert all(r['lm']==r['qty']*2.5 for r in rows)
    assert any(r['kind']=='channel' for r in rows)==(name!='fryserom')
    data=cutting_pdf(selection,'beslagprofiler')
    doc=PdfReader(io.BytesIO(data))
    assert len(doc.pages) <= 2,(name,len(doc.pages))
    text='\n'.join(page.extract_text() for page in doc.pages)
    for value in ('RAL 9010','0,6 mm','2500 mm','TOTAL BESTILLING','138','Stramo AS','Side 1'):
        assert value in text,(name,value)
    assert sum(len(page.images) for page in doc.pages)>=len(rows)
    assert 'ombrett' not in text and 'MÅLTEGNINGER OG BESTILLING' not in text
    assert 'løpemeter' not in text and 'LM' in text
    for r in rows:
        assert f"{r['qty']} stk" in text
    Path(f'output/pdf/Tasty-beslagsliste-{name}.pdf').write_bytes(data)
    rendered=pdfium.PdfDocument(data)
    rendered[0].render(scale=1.5).to_pil().save(f'tmp/pdfs/profiler-{name}-0.png')
for room in rooms:
    inp=world_input(room)
    calc=beregn_prosjekt(inp)['df_mat']
    channels=calc[calc.Post.str.startswith('U-kanal')]
    assert channels.empty==(inp.rom_type=='Fryserom')
    if not channels.empty:
        row=next(r for r in profile_rows(project_materials([room])) if r['kind']=='channel')
        assert row['qty']==int(channels.Mengde.sum())
        assert '2500 mm' in channels.iloc[0].Type
colli=packages(rooms)
assert (colli[colli.Innhold.str.contains('U-kanal|2500 mm')].Lengde_mm==2540).all()
for kind in ('alle','beslag','materialer'):
    data=cutting_pdf(rooms,kind)
    assert 'RAL 9010' in '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    Path(f'output/pdf/oppdatert-{kind}.pdf').write_bytes(data)
print('PASS: profile PDF, selected rooms, totals, calculation, material list and transport')
