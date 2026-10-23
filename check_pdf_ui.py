import faulthandler
from pathlib import Path
from streamlit.testing.v1 import AppTest
from project_file import decode_project
faulthandler.dump_traceback_later(55,exit=True)
a=AppTest.from_file('app.py',default_timeout=30).run()
assert not any(n.key in ('ed_panel_weight','ed_waste_pct') for n in a.number_input)
assert any('Automatisk panelvekt:' in c.value for c in a.caption)
a.session_state['project_rooms']=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
a.radio(key='ed_module').set_value('Rom og sammenstilling').run()
assert not a.exception,[e.message for e in a.exception]
labels=[b.label for b in a.get('download_button')]
assert 'Materialliste hele prosjektet – PDF' in labels,labels
assert 'Alle kapplister samlet – PDF' in labels,labels
assert 'Gulvplatekapplister – PDF' in labels,labels
assert 'Detaljert beslagsliste – PDF' in labels,labels
assert any('Produkt' in d.value.columns for d in a.dataframe)
room_id=a.session_state['project_rooms'][1]['id']
a.selectbox(key='export_room_choice').set_value(room_id).run()
assert not a.exception,[e.message for e in a.exception]
labels=[b.label for b in a.get('download_button')]
assert 'Materialliste valgt rom – PDF' in labels
frames=[d.value for d in a.dataframe if 'Tykkelse (mm)' in d.value.columns and 'Produkt' in d.value.columns]
assert len(frames)==1
assert not frames[0].Produkt.str.contains('PIR 80').any()
assert frames[0].Produkt.str.contains('PIR 100').any()
a.selectbox(key='export_room_choice').set_value('Alle rom').run()
assert not a.exception,[e.message for e in a.exception]
assert any(d.value.Produkt.str.contains('PIR 80').any() for d in a.dataframe if 'Produkt' in d.value.columns)
faulthandler.cancel_dump_traceback_later()
print('PASS: assembly material PDF/CSV and all four cutting PDF downloads')
