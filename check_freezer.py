"""Run with Python and the app dependencies plus ifcopenshell installed."""
from pathlib import Path
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ifcopenshell
import ifcopenshell.geom
from geometry import l_polygon, poly_area
from construction import finished_floor, floor_depth, door_keys, wall_base, floor_outline
from database import DOR_DB, PANEL_DB
from kalkulasjon import ProjectInput, beregn_prosjekt
from montasje import tegn_snitt, tegn_taktegning, tegn_3d_modell, tegn_veggoppstaltt
from ifc_export import gen_ifc


def run():
    out = Path(__file__).parent / "qa"
    out.mkdir(exist_ok=True)
    shapes = {
        "rectangle": [(0,0),(4,0),(4,3),(0,3)],
        "L": [(0,0),(6,0),(6,3),(3,3),(3,5),(0,5)],
        "cut_corner": [(0,0),(6,0),(6,3),(5,4),(0,4)],
    }
    shapes["L_user_left"] = l_polygon([8720,6685,4860,2410,3860,9095])
    shapes["L_user_right"] = l_polygon([8720,9095,4860,2410,3860,6685])
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    count = 0
    for name, pts in shapes.items():
        for room in ("Kjølerom", "Fryserom"):
            for panel in ("PIR 100 mm", "PIR 150 mm"):
                door = door_keys(room, DOR_DB)[0]
                inp = ProjectInput("Kontroll", "", "", "", "1:50", room,
                                   panel, pts, 2.5, 1.1, [(door,1,0,.35)], [])
                result = beregn_prosjekt(inp)
                assert result["ov"]["V"] == round(poly_area(pts)*(2.5-floor_depth(room)),2)
                mat = result["df_mat"]
                channels = mat[mat.Post.str.startswith("U-kanal")]
                width = int(panel.split()[1])
                assert channels.empty == (room == 'Fryserom')
                if room == 'Kjølerom':
                    assert str(width) in channels.iloc[0].Post
                    assert channels.iloc[0].Mengde == math.ceil(result['ov']['P']*1.1/2.5-1e-10)
                floor_rows = mat[mat.Post.str.startswith("Gulv")]
                assert len(floor_rows) >= (2 if room == "Fryserom" else 0)
                if room == "Fryserom":
                    assert floor_rows.iloc[0]["Mengde"] >= poly_area(floor_outline(pts,width/1000))-.01
                data = gen_ifc(pts,2.5,"Kontroll",panel,inp.dorer,room,1.1)
                model = ifcopenshell.file.from_string(data.decode("utf-8"))
                floors = [s for s in model.by_type("IfcSlab") if __import__('re').match(r'^G\d',s.Name or '')]
                boards = [s for s in model.by_type("IfcSlab") if s.Name.startswith("Gulvplate")]
                assert len(floors) == result["sam"]["gulv"]
                assert len(boards) == (1 if room == "Fryserom" else 0)
                assert len(model.by_type("IfcBuildingElementProxy")) == (0 if room == "Fryserom" else len(pts))
                for element in floors + boards + list(model.by_type("IfcDoor")) + list(model.by_type("IfcBuildingElementProxy")):
                    shape = ifcopenshell.geom.create_shape(settings,element)
                    mesh = shape.geometry
                    coords = np.array(mesh.verts).reshape(-1,3)
                    lo, hi = coords.min(axis=0), coords.max(axis=0)
                    if element in floors:
                        assert np.allclose([lo[2],hi[2]],[.022,.022+width/1000])
                    elif element in boards:
                        assert np.allclose([lo[2],hi[2]],[wall_base(room,panel),wall_base(room,panel)+.012])
                    elif element.is_a("IfcDoor"):
                        assert np.allclose([lo[2],hi[2]],[finished_floor(room,panel),finished_floor(room,panel)+2.1])
                    else:
                        assert np.allclose([lo[2],hi[2]],[wall_base(room,panel),wall_base(room,panel)+.080] if room == "Fryserom" else [0,.050])
                fig3 = tegn_3d_modell(inp)
                doors = [t for t in fig3.data if t.name.startswith("Dør –")]
                assert np.isclose(min(doors[0].z),finished_floor(room,panel))
                assert any(t.name == f"U-kanal {width} mm" for t in fig3.data) == (room == "Kjølerom")
                if room == "Fryserom":
                    assert any(t.name == "Gulvplate 12 mm" and np.isclose(max(t.z),finished_floor(room,panel)) for t in fig3.data)
                section = tegn_snitt(inp,result)
                roof = tegn_taktegning(inp,result)
                elevation = tegn_veggoppstaltt(inp,result)
                door_patches = [p for p in elevation.axes[0].patches if np.isclose(p.get_height(),2.1)]
                assert any(np.isclose(p.get_y(),floor_depth(room)) for p in door_patches)
                if name == "rectangle" and panel == "PIR 150 mm":
                    tag = "freezer" if room == "Fryserom" else "cooler"
                    section.savefig(out / f"{tag}-section.png",dpi=100)
                    elevation.savefig(out / f"{tag}-wall.png",dpi=100)
                    fig3.write_html(out / f"{tag}-3d.html",include_plotlyjs=True)
                    (out / f"{tag}.ifc").write_bytes(data)
                plt.close("all")
                count += 1
    print(f"PASS: {count} cases, calculation, 2D, 3D and parsed IFC geometry")


if __name__ == "__main__":
    run()

