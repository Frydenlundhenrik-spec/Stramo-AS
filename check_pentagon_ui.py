"""Editable pentagon walls, exact project round trips and independent rooms."""
from copy import deepcopy
import math

import numpy as np
from streamlit.testing.v1 import AppTest

from geometry import wall_lengths
from project_file import decode_project, encode_project


app = AppTest.from_file("app.py", default_timeout=60).run()


def checked():
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error, [e.value for e in app.error]


def values():
    return [app.number_input(key=f"ed_pentagon_side_{i}").value for i in range(5)]


def change(index, value):
    app.number_input(key=f"ed_pentagon_side_{index}").set_value(float(value)).run()
    checked()


checked()
app.number_input(key="ed_doors").set_value(0)
app.selectbox(key="ed_shape").set_value("Femkant – avskåret hjørne").run()
checked()
assert "Femkant med skråvegg" in app.selectbox(key="ed_shape").options
assert not any("Avskjær" in item.label for item in app.number_input)
assert all(f"Vegg {i+1}" in app.number_input(key=f"ed_pentagon_side_{i}").label for i in range(5))
initial = [5850, 3350, math.hypot(1100, 1100), 4750, 4450]
assert np.allclose(values(), initial)

# Every straight wall is editable; the diagonal follows the resulting endpoints.
for index, length in ((0, 6000), (1, 3100), (4, 4600), (3, 4500)):
    change(index, length)
    sides = values()
    assert sides[index] == length
    assert math.isclose(sides[2], math.hypot(sides[0]-sides[3], sides[4]-sides[1]), abs_tol=1e-8)

# Editing the diagonal can move either adjoining endpoint, preserving the totals.
change(2, 2500)
assert np.allclose(values(), [6000, 3100, 2500, 4000, 4600])
app.selectbox(key="ed_pentagon_adjust").set_value(1).run()
change(2, 2600)
expected = [6000, 4600-math.sqrt(2600**2-2000**2), 2600, 4000, 4600]
assert np.allclose(values(), expected, atol=1e-8, rtol=0)
assert not float(values()[1]).is_integer(), "Do not round away exact geometry."

# Invalid edits must keep the last valid room instead of corrupting its snapshot.
before = deepcopy(app.session_state["last_valid_editor"])
change(2, 100)
assert np.allclose(values(), expected, atol=1e-8, rtol=0)
assert app.warning
assert app.session_state["last_valid_editor"]["input"]["pts"] == before["input"]["pts"]
change(3, 6100)
assert np.allclose(values(), expected, atol=1e-8, rtol=0)
assert app.warning
change(2, 2600)

app.text_input(key="ed_name").set_value("Femkant med presise mål").run()
app.button(key="add_finished_room").click().run()
checked()
saved = deepcopy(app.session_state["project_rooms"][0])
assert saved["form"]["kind"] == "Femkant – avskåret hjørne"
assert all(key in saved["form"] for key in ("length_mm", "width_mm", "cut_x_mm", "cut_y_mm"))
project = decode_project(encode_project([saved], saved, saved["id"]))
assert np.allclose(project["rooms"][0]["input"]["pts"], saved["input"]["pts"], atol=1e-12, rtol=0)
app.session_state["pending_editor"] = deepcopy(project["rooms"][0])
app.run()
checked()
assert np.allclose(values(), expected, atol=1e-8, rtol=0)
assert app.selectbox(key="ed_pentagon_adjust").value == 1

# Older project files have no preferred adjoining wall; they use wall 4.
legacy = deepcopy(saved)
legacy["form"].pop("diagonal_adjust_wall", None)
app.session_state["pending_editor"] = legacy
app.run()
checked()
assert np.allclose(values(), expected, atol=1e-8, rtol=0)
assert app.selectbox(key="ed_pentagon_adjust").value == 3

# New rooms must not inherit the previous pentagon's edited dimensions.
app.button(key="new_freezer_room").click().run()
checked()
app.selectbox(key="ed_shape").set_value("Femkant – avskåret hjørne").run()
checked()
assert np.allclose(values(), initial)
assert app.number_input(key="ed_doors").value == 0
assert np.allclose(app.session_state["project_rooms"][0]["input"]["pts"], saved["input"]["pts"])
app.button(key="add_finished_room").click().run()
checked()
assert len(app.session_state["project_rooms"]) == 2
app.selectbox(key="room_picker").set_value(saved["id"]).run()
checked()
assert np.allclose(values(), expected, atol=1e-8, rtol=0)

# Existing orthogonal L editing retains its six-wall closure rules.
app.selectbox(key="ed_shape").set_value("L-form").run()
checked()
app.number_input(key="l_side_0").set_value(6000).run()
checked()
assert app.number_input(key="l_side_2").value + app.number_input(key="l_side_4").value == 6000
assert len(wall_lengths(app.session_state["last_valid_editor"]["input"]["pts"])) == 6

# Small rectangles need proportional initial cuts instead of the default 1100 mm.
app.button(key="new_cool_room").click().run()
checked()
app.selectbox(key="ed_shape").set_value("Rektangel").run()
checked()
app.number_input(key="ed_length").set_value(500)
app.number_input(key="ed_width").set_value(500).run()
checked()
app.selectbox(key="ed_shape").set_value("Femkant – avskåret hjørne").run()
checked()
assert np.allclose(values(), [500, 250, math.hypot(250, 250), 250, 500])
assert len(wall_lengths(app.session_state["last_valid_editor"]["input"]["pts"])) == 5
change(0, 700)
change(4, 800)
app.selectbox(key="ed_shape").set_value("Rektangel").run()
checked()
assert app.number_input(key="ed_length").value == 700
assert app.number_input(key="ed_width").value == 800
print("PASS: five editable walls, automatic diagonal, both neighbours, rejected invalid edits, exact save/restore, independent rooms, L-form and rectangle transitions")
