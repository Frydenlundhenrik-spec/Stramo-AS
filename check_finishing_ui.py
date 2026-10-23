from pathlib import Path
import faulthandler
from streamlit.testing.v1 import AppTest
from project_file import decode_project
faulthandler.dump_traceback_later(50,exit=True)
p=decode_project(Path('Tasty-Rom4-og-fryserom.json').read_bytes())
a=AppTest.from_file('app.py',default_timeout=20).run()
a.session_state['project_rooms']=p['rooms']
a.session_state['pending_editor']=p['rooms'][1]
a.run()
assert not a.exception,[e.message for e in a.exception]
assert a.number_input(key='ed_finer_width').value==1220
a.number_input(key='ed_finer_width').set_value(1250).run()
a.button(key='calculate_finishing').click().run()
assert not a.exception,[e.message for e in a.exception]
assert any('gulvfiberplater' in m.value for m in a.markdown)
a.radio(key='ed_module').set_value('Rom og sammenstilling').run()
assert not a.exception,[e.message for e in a.exception]
assert a.session_state['project_rooms'][1]['form']['plywood_width_mm']==1250
assert a.session_state['project_rooms'][0]['excluded_walls']==[3,4]
faulthandler.cancel_dump_traceback_later()
print('PASS: button, adjustable plywood sheet format, assembled rooms and persisted fields')
