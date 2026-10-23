"""Final UI integration: actual exports, six modules, validation and shared prices."""
import copy
import io
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

import build_standard_fdv
from kalkulasjon import beregn_prosjekt
from project_file import decode_project, world_input


def checked(app):
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error, [e.value for e in app.error]


def check():
    project = decode_project(Path("Tasty-Rom4-og-fryserom-med-dorer.json").read_bytes())
    app = AppTest.from_file("app.py", default_timeout=100).run()
    checked(app)
    app.session_state["project_rooms"] = copy.deepcopy(project["rooms"])
    app.session_state["pending_editor"] = copy.deepcopy(project["rooms"][0])
    app.run()
    checked(app)
    actual_builder = build_standard_fdv.lag_standard_fdv_pdf
    generated = []

    def record_fdv(*args, **kwargs):
        data = actual_builder(*args, **kwargs)
        generated.append((args, data))
        return data

    with patch.object(build_standard_fdv, "lag_standard_fdv_pdf", side_effect=record_fdv):
        for module in app.radio(key="ed_module").options:
            app.radio(key="ed_module").set_value(module).run()
            checked(app)
            if module == "FDV":
                labels = [button.label for button in app.get("download_button")]
                assert "Last ned standard FDV PDF" in labels, labels
                scope = next(radio for radio in app.radio if radio.label == "FDV for")
                scope.set_value("Hele prosjektet").run()
                checked(app)
                args, data = generated[-1]
                assert set(args[2]) == {r["input"]["navn"] for r in project["rooms"]}
                reader = PdfReader(io.BytesIO(data))
                assert len(reader.pages) == 244, len(reader.pages)
                overview = "\n".join(page.extract_text() or "" for page in reader.pages[:5])
                assert "PE25" in overview and "25 µm" in overview
                assert all(r["input"]["navn"] in overview for r in project["rooms"])
                assert "Ettersendes" in overview
                assert "Skruer" in overview and "Fugemasse" in overview and "Gulvfiberplater" in overview
    print("PASS: all six UI modules; FDV download uses actual 244-page pack, both rooms, PE25 and pending-document slots")

    app = AppTest.from_file("app.py", default_timeout=60).run()
    app.number_input(key="ed_doors").set_value(2).run()
    app.number_input(key="do1").set_value(2000).run()
    checked(app)
    prices = [widget for widget in app.number_input if str(widget.key).startswith("door_price_")]
    assert len(prices) == 1, [w.key for w in prices]
    prices[0].set_value(20000.0).run()
    checked(app)
    app.number_input(key="ed_screw_price").set_value(2.5).run()
    checked(app)
    room = copy.deepcopy(app.session_state["last_valid_editor"])
    door_key = room["input"]["dorer"][0][0]
    assert room["prices"][f"dor_{door_key}"] == 20000
    assert room["prices"]["skruer"] == 2.5
    material = beregn_prosjekt(world_input(room), room["prices"])["df_mat"]
    assert material.loc[material.Post == "Dør", "Totalpris (kr)"].sum() == 40000
    app.text_input(key="ed_pnr").set_value("138").run()
    app.button(key="new_cool_room").click().run()
    checked(app)
    assert app.number_input(key="ed_screw_price").value == 2.5
    assert app.text_input(key="ed_pnr").value == "138"
    assert app.session_state["pris_override"][f"dor_{door_key}"] == 20000
    app.number_input(key="ed_doors").set_value(1).run()
    checked(app)
    inherited = next(w for w in app.number_input if str(w.key).startswith("door_price_"))
    assert inherited.value == 20000
    print("PASS: duplicate door products share one price; both doors priced; new room inherits screw/door prices and project number")

    app.selectbox(key="ed_shape").set_value("Egendefinert polygon").run()
    checked(app)
    app.number_input(key="ed_corners").set_value(4).run()
    checked(app)
    before = copy.deepcopy(app.session_state["last_valid_editor"])
    for i, (x, y) in enumerate(((0,0),(5000,4000),(0,4000),(4000,0))):
        app.session_state[f"px{i}"] = float(x)
        app.session_state[f"py{i}"] = float(y)
    app.run()
    assert app.error and not app.exception
    assert any("krysser" in error.value for error in app.error)
    assert app.session_state["last_valid_editor"] == before
    assert app.button(key="new_cool_room")
    print("PASS: self-crossing polygon shows validation error without crash; last valid room and recovery controls remain")


if __name__ == "__main__":
    check()
