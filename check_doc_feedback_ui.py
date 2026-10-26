import faulthandler
from streamlit.testing.v1 import AppTest
from database import DOR_DB
faulthandler.dump_traceback_later(180,exit=True)
a=AppTest.from_file('app.py',default_timeout=100).run()
assert not a.exception,[e.message for e in a.exception]
assert DOR_DB[a.selectbox(key='dt_Kjølerom_0').value]['bw']==1000
# No doors while testing removal of their host wall.
a.number_input(key='ed_doors').set_value(0).run()
a.radio(key='ed_module').set_value('Montasjetegninger').run()
assert not a.exception,[e.message for e in a.exception]
a.multiselect(key='ed_drawing_walls').set_value([0]).run()
assert not a.exception,[e.message for e in a.exception]
assert a.session_state['last_valid_editor']['excluded_walls']==[0]
assert all(not s.value.startswith('Vegg 1 ') for s in a.selectbox if s.label in ('Velg snitt-vegg','Velg vegg'))
a.radio(key='ed_module').set_value('Elementer').run()
assert not a.exception,[e.message for e in a.exception]
assert a.session_state['last_valid_editor']['excluded_walls']==[0]
faulthandler.cancel_dump_traceback_later()
print('PASS: default 1m door, wall removal in drawings persists into cutlists')

