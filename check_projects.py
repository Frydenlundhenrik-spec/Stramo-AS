"""Round-trip projects and verify final wall exclusions across outputs."""
import copy
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ifcopenshell
import ifcopenshell.geom
from database import PANEL_DB
from kalkulasjon import ProjectInput, beregn_prosjekt
from project_file import (make_room, validate_room, encode_project, decode_project,
                          world_input, snap_room, freezer_shared_walls, form_points)
from project_ui import assembly_plan
from montasje import tegn_3d_modell
from ifc_export import gen_ifc


def check():
    rooms = []
    for room_type, name, length, door,wall in (
        ("Fryserom","Frys",4000,"Fryserom enkel 900×2100 mm",0),
        ("Kjølerom","Kjøl",6000,"Enkel kjøledør 900×2100 mm",3),
    ):
        form = dict(kind="Rektangel",length_mm=length,width_mm=3000)
        inp = ProjectInput(name,"42","A10","21.10.2026","1:50",room_type,"PIR 150 mm",
                           form_points(form),2.5,1.1,[(door,1,wall,.35,"Venstre")],[])
        rooms.append(make_room(inp,form,{}))
    freezer,cooler = rooms
    cooler["position_mm"] = snap_room(cooler,3,freezer,1)
    assert np.allclose(cooler["position_mm"],[4150,0])
    assert freezer_shared_walls(rooms)==[(cooler["id"],3,freezer["id"],1)]
    before = beregn_prosjekt(world_input(cooler))
    cooler["excluded_walls"] = [3]
    for r in rooms:
        validate_room(r)
    after = beregn_prosjekt(world_input(cooler))
    assert "Vegg 4" not in set(after["df_mat"].Post)
    assert "Dør" not in set(after["df_mat"].Post)
    assert "Vegg 4" not in set(after["df_kapp"].Vegg)
    assert after["tot_pris"] < before["tot_pris"]
    assert after["sam"]["tak"] == before["sam"]["tak"]
    fig3 = tegn_3d_modell(world_input(cooler))
    assert not any(t.name.startswith("Vegg 4") or t.name.startswith("Dør –") for t in fig3.data)
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS,True)
    inp = world_input(cooler)
    model = ifcopenshell.file.from_string(gen_ifc(inp.pts,inp.hoyde_m,inp.navn,inp.panel_key,
        inp.dorer,inp.rom_type,inp.panelbredde_m,excluded_walls=inp.excluded_walls).decode())
    assert len(model.by_type("IfcWall"))==3
    assert len(model.by_type("IfcBuildingElementProxy"))==3
    assert not model.by_type("IfcDoor")
    for wall in model.by_type("IfcWall"):
        shape = ifcopenshell.geom.create_shape(settings,wall)
        assert shape.geometry.verts
    raw = encode_project(rooms,cooler,cooler["id"])
    loaded = decode_project(raw)
    assert encode_project(loaded["rooms"],loaded["draft"],loaded["active_id"]) == raw
    assert beregn_prosjekt(world_input(loaded["rooms"][1]))["tot_pris"] == after["tot_pris"]
    # Reject unsupported/corrupted files without normalizing them into something else.
    for mutate in (
        lambda p:p.update(version=99),
        lambda p:p["rooms"][0]["input"].update(panelbredde_m=0),
        lambda p:p["rooms"][0]["input"]["pts"][0].__setitem__(0,99),
        lambda p:p["rooms"][0].update(excluded_walls=[99]),
    ):
        bad = json.loads(raw)
        mutate(bad)
        try:
            decode_project(json.dumps(bad).encode())
        except ValueError:
            pass
        else:
            raise AssertionError("Corrupt project accepted")
    # Editable L parameters, transforms, door pricing and openings round-trip too.
    form = dict(kind="L-form",sides_mm=[8720,9095,4860,2410,3860,6685],turns=1,mirrored=True)
    data = copy.deepcopy(freezer["input"])
    data.update(pts=form_points(form),dorer=[("Fryserom enkel 1000×2100 mm",1,2,.35,"Høyre")],
                apninger=[(0,.3,1.,1.,.3,"Åpning")])
    extra = make_room(ProjectInput(**data),form,{"dor_Fryserom enkel 1000×2100 mm":20000})
    validate_room(extra)
    assert decode_project(encode_project([extra],extra,extra["id"]))["draft"]["form"]==form
    out = Path(__file__).parent/"qa"
    out.mkdir(exist_ok=True)
    (out/"eksempel-flerrom.json").write_bytes(raw)
    fig = assembly_plan(rooms)
    fig.savefig(out/"sammenstilling.png",dpi=110)
    plt.close(fig)
    print("PASS: project round-trip, invalid files, snapping, shared freezer wall, quantities, cut list, 3D and IFC")


if __name__ == "__main__":
    check()
