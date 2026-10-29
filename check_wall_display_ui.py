"""Tasty wall table, aligned order columns and full-height material view."""
from copy import deepcopy
from pathlib import Path
import json
from streamlit.testing.v1 import AppTest
from project_file import decode_project

rooms=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
for r in rooms:
    r['input']['navn'] += ' – bildetest'
app=AppTest.from_file('app.py', default_timeout=120).run()
app.session_state['project_rooms']=deepcopy(rooms)
app.session_state['pending_editor']=deepcopy(rooms[0])
app.run()
app.radio(key='ed_module').set_value('Tegninger').run()
assert not app.exception, [e.message for e in app.exception]
wall_table=next(d.value for d in app.dataframe if 'Utvendig lengde (m)' in d.value.columns)
assert wall_table.Vegg.tolist()==[f'Vegg {i}' for i in range(1,7)]
assert wall_table['Utvendig lengde (mm)'].tolist()==[8960,8910,6330,5050,2550,3780]
assert not any('bildetest' in m.value.lower() for m in app.markdown)
app.radio(key='ed_module').set_value('Bestilling').run()
assert not app.exception, [e.message for e in app.exception]
configs=[]
for title in ('Beslag','Dører','Tilbehør'):
    table=next(d for d in app.dataframe if title in d.value.columns)
    config=json.loads(table.proto.columns)
    configs.append([config[c]['width'] for c in (title,'Antall','Enhet')])
    assert not table.value[title].str.contains('bildetest').any()
assert configs==[[700,120,150]]*3
app.radio(key='ed_module').set_value('Kalkulasjon').run()
assert not app.exception, [e.message for e in app.exception]
table=next(d for d in app.dataframe if 'Totalpris (kr)' in d.value.columns)
assert table.value.iloc[-1].Post=='SUM'
assert len(app.session_state['project_rooms'])==2
print('PASS: Tasty wall labels/lengths, stable order columns, clean names and material totals')
