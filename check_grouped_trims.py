from pathlib import Path
from collections import defaultdict
import re
from pypdf import PdfReader
from finishing import grouped_trim_bars,trim_cuts
from project_file import decode_project,world_input
from kalkulasjon import beregn_prosjekt
from cutlist_pdf import cutting_pdf,project_materials

sample=[dict(Profil='50x50',**r) for r in trim_cuts([('V1',5),('V2',5)])]
grouped=grouped_trim_bars(sample)
assert grouped==[dict(Profil='50x50',Antall_stenger=4,Kapp_pr_stang='2500 mm',Rest_pr_stang_mm=0,Løpemeter=10.)]
assert len(grouped_trim_bars(sample+[dict(sample[0],Profil='50x150')]))==2
rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
rows=[]
for room in rooms:
    bb=beregn_prosjekt(world_input(room))['beslag']
    for profile,key in [('50x50','kapp_inn'),('50x150','kapp_ut')]:
        rows.extend(dict(Profil=profile,**r) for r in bb[key])
grouped=grouped_trim_bars(rows)
for profile in ('50x50','50x150'):
    old=[r for r in rows if r['Profil']==profile];new=[r for r in grouped if r['Profil']==profile]
    full=sum(r['Kapp'].startswith('2500 mm (') and r['Rest_mm']==0 for r in old)
    combined=[r for r in new if r['Kapp_pr_stang']=='2500 mm']
    assert len(combined)==1 and combined[0]['Antall_stenger']==full
    assert sum(r['Antall_stenger'] for r in new)==len(old)
    assert sum(r['Rest_pr_stang_mm']*r['Antall_stenger'] for r in new)==sum(r['Rest_mm'] for r in old)
    assert sum(sum(map(int,re.findall(r'(\d+) mm',r['Kapp_pr_stang'])))*r['Antall_stenger'] for r in new)==sum(2500-r['Rest_mm'] for r in old)
data=cutting_pdf(rooms,'beslag')
Path('output/pdf/kontroll-grupperte-beslag.pdf').write_bytes(data)
pdf=PdfReader('output/pdf/kontroll-grupperte-beslag.pdf')
text='\n'.join(p.extract_text() for p in pdf.pages)
assert len(pdf.pages)==1
assert 'like lengder samlet' not in text and 'Antall stenger' not in text
assert 'TOTAL BESTILLING' in text and '94 stk' in text and '235 LM' in text
assert project_materials(rooms).query("Gruppe == 'Elementer'").Stk.sum()==75
print('PASS: internal trim cuts conserved; detailed cut pages removed; one profile page retains 94 bars and 235 LM')
