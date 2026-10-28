"""Ordering previews and selected-room export now live under Produksjon."""
from pathlib import Path
from streamlit.testing.v1 import AppTest
from project_file import decode_project

p=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())
a=AppTest.from_file('app.py',default_timeout=90)
a.session_state['pending_project']=p
a.run()
a.radio(key='ed_module').set_value('Produksjon').run()
assert not a.exception,[e.message for e in a.exception]
a.selectbox(key='doc_production_preview').set_value('Bestillingslister').run()
assert a.checkbox(key='doc_production_profiles').value
assert a.checkbox(key='doc_production_floor_cuts').value
assert a.checkbox(key='doc_production_panel_order').value
assert a.checkbox(key='doc_production_accessory_order').value
room_id=p['rooms'][1]['id']
a.multiselect(key='doc_production_rooms').set_value([room_id]).run()
assert not a.exception,[e.message for e in a.exception]
frames=[d.value for d in a.dataframe if 'Tykkelse (mm)' in d.value.columns and 'Produkt' in d.value.columns]
assert len(frames)==1
assert not frames[0].Produkt.str.contains('PIR 80').any()
assert frames[0].Produkt.str.contains('PIR 100').any()
a.multiselect(key='doc_production_rooms').set_value([r['id'] for r in p['rooms']]).run()
assert not a.exception,[e.message for e in a.exception]
assert any(d.value.Produkt.str.contains('PIR 80').any() for d in a.dataframe if 'Produkt' in d.value.columns)
assert not any('CSV' in b.label or 'Excel' in b.label for b in a.get('download_button'))
print('PASS: grouped order previews for one/all rooms and selectable combined PDF under Produksjon')
