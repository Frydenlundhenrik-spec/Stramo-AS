"""Room recovery must synchronize the selected module with the browser."""
import copy
from pathlib import Path

from streamlit.testing.v1 import AppTest

from project_file import decode_project


project = decode_project(Path("Tasty-Rom4-og-fryserom-med-dorer.json").read_bytes())
app = AppTest.from_file("app.py", default_timeout=90).run()
app.session_state["project_rooms"] = copy.deepcopy(project["rooms"])
app.session_state["pending_editor"] = copy.deepcopy(project["rooms"][0])
app.run()
app.radio(key="ed_module").set_value("Transport").run()
transport_id = app.radio(key="ed_module").proto.id
app.selectbox(key="recover_room_choice").set_value(project["rooms"][1]["id"]).run()
app.button(key="recover_room").click().run()
assert not app.exception, [e.message for e in app.exception]
assert not app.error, [e.value for e in app.error]
module = app.radio(key="ed_module")
print("Recovered module:", module.value, "same widget:", module.proto.id == transport_id,
      "set_value:", module.proto.set_value, "wire value:", module.proto.raw_value, flush=True)
assert module.value == "Kalkulasjon"
assert app.radio(key="ed_room_type").value == "Fryserom"
assert app.text_input(key="ed_name").value == project["rooms"][1]["input"]["navn"]
# A browser retains the old selection for this stable widget ID unless the
# server explicitly sends the replacement value. AppTest's .value alone reads
# server state and therefore does not detect a visually stale radio button.
assert module.proto.id != transport_id or module.proto.set_value, "The browser is not told to deselect Transport after room recovery"
assert module.proto.raw_value == "Kalkulasjon"
print("PASS: upper room-recovery control shows the freezer and explicitly synchronizes Kalkulasjon selection")
