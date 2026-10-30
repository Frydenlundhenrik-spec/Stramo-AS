"""Friday editor requirements across every room shape, including project reloads."""
from copy import deepcopy

import numpy as np
from streamlit.testing.v1 import AppTest

from database import FORM_MALER
from geometry import wall_lengths, poly_area
from project_file import decode_project, encode_project, form_points, validate_room


app = AppTest.from_file("app.py", default_timeout=90).run()


def checked():
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error, [e.value for e in app.error]


def current():
    return deepcopy(app.session_state["last_valid_editor"])


checked()
for shape in FORM_MALER:
    app.button(key="new_cool_room").click().run()
    checked()
    assert app.number_input(key="ed_height").value == 2500
    app.selectbox(key="ed_shape").set_value(shape).run()
    checked()
    for key in ("ed_rotate", "ed_mirror", "ed_reset"):
        assert app.button(key=key)
    if shape == "Egendefinert polygon":
        assert all(item.proto.format == "%.0f" for item in app.number_input
                   if item.key and item.key.startswith(("px", "py")))
    base = current()
    base_points = form_points(base["form"])
    app.button(key="ed_rotate").click().run()
    checked()
    rotated = current()
    assert rotated["form"]["turns"] == 1
    assert not np.allclose(form_points(rotated["form"]), base_points)
    app.button(key="ed_mirror").click().run()
    checked()
    changed = current()
    assert changed["form"]["mirrored"] is True
    assert np.allclose(wall_lengths(form_points(changed["form"])), wall_lengths(base_points))
    assert np.isclose(poly_area(form_points(changed["form"])), poly_area(base_points))
    validate_room(changed)
    restored = decode_project(encode_project([], changed, None))
    app.session_state["pending_project"] = restored
    app.run()
    checked()
    assert np.allclose(current()["input"]["pts"], changed["input"]["pts"], atol=1e-12, rtol=0)
    assert current()["form"]["turns"] == changed["form"]["turns"]
    assert current()["form"]["mirrored"] is True
    app.button(key="ed_reset").click().run()
    checked()
    assert np.allclose(form_points(current()["form"]), base_points, atol=1e-12, rtol=0)
    assert current()["form"]["turns"] == 0
    assert current()["form"]["mirrored"] is False

# Existing project heights must remain unchanged; only new rooms use 2500 mm.
app.number_input(key="ed_height").set_value(2400).run()
checked()
saved = current()
app.session_state["pending_project"] = decode_project(encode_project([saved], saved, saved["id"]))
app.run()
checked()
assert app.number_input(key="ed_height").value == 2400
app.button(key="new_freezer_room").click().run()
checked()
assert app.number_input(key="ed_height").value == 2500

# The plan wall table displays each length only once, in whole millimetres.
app.selectbox(key="ed_shape").set_value("L-form").run()
app.radio(key="ed_module").set_value("Tegninger").run()
checked()
tables = [item.value for item in app.dataframe
          if "Utvendig lengde (mm)" in item.value.columns]
assert len(tables) == 1
table = tables[0]
assert "Utvendig lengde (m)" not in table.columns
assert table["Vegg"].tolist() == [f"Vegg {i}" for i in range(1, 7)]
assert all(float(v).is_integer() for v in table["Utvendig lengde (mm)"])
assert table["Utvendig lengde (mm)"].tolist() == [5850, 4450, 2925, 2225, 2925, 2225]
print("PASS: every form rotates, mirrors, resets and reloads; original heights preserved; new rooms 2500 mm; wall table only whole mm")
