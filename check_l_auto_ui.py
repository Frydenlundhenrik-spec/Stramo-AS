import faulthandler
from streamlit.testing.v1 import AppTest
faulthandler.dump_traceback_later(50,exit=True)
a=AppTest.from_file('app.py',default_timeout=15).run()
a.selectbox(key='ed_shape').set_value('L-form').run()
def change(i,v):
 a.number_input(key=f'l_side_{i}').set_value(v).run()
 assert not a.exception,[e.message for e in a.exception]
def vals(): return [a.number_input(key=f'l_side_{i}').value for i in range(6)]
change(0,8960); change(1,8910); change(2,6410); change(5,3860)
assert vals()==[8960,8910,6410,5050,2550,3860],vals()
change(4,2410)
assert vals()==[8960,8910,6550,5050,2410,3860],vals()
change(2,6410)
change(3,4860)
assert vals()==[8960,8910,6410,4860,2550,4050],vals()
change(1,9000)
assert vals()==[8960,9000,6410,4860,2550,4140],vals()
before=vals(); change(4,10000); assert vals()==before
for key in ['l_rotate','l_mirror']:
 a.button(key=key).click().run(); assert vals()==before; assert not a.exception
# Old project orientation with V6 as height must keep that total too.
for i,v in enumerate([8720,6685,4860,2410,3860,9095]):
 a.session_state[f'l_side_{i}']=v
a.run(); change(1,6500)
assert vals()==[8720,6500,4860,2595,3860,9095],vals()
faulthandler.cancel_dump_traceback_later()
print('PASS: bidirectional parts, total changes, invalid input, rotation/mirror and old orientation')
