import faulthandler
from pathlib import Path
from streamlit.testing.v1 import AppTest
from project_file import decode_project
faulthandler.dump_traceback_later(50,exit=True)
a=AppTest.from_file('app.py',default_timeout=30).run()
a.session_state['project_rooms']=decode_project(Path('Tasty-Rom4-og-fryserom-med-dorer.json').read_bytes())['rooms']
a.radio(key='ed_module').set_value('Transport').run()
assert not a.exception,[e.message for e in a.exception]
assert len(a.get('plotly_chart'))==1
assert any('Registrert vekt'==m.label for m in a.metric)
assert any('transportliste' in d.label.lower() for d in a.get('download_button'))
assert any('Elementer og beslag' in c.value and 'fronten' in c.value for c in a.caption)
assert next(m.value for m in a.metric if m.label=='Plasserte kolli')=='12 / 12'
faulthandler.cancel_dump_traceback_later()
print('PASS: Transport module with all project rooms, 3D and downloads')
