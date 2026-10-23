from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ifcopenshell
import ifcopenshell.geom
from geometry import l_polygon, transform_polygon, wall_lengths, polygon_winding
from kalkulasjon import ProjectInput, beregn_prosjekt
from montasje import tegn_plantegning, tegn_3d_modell
from ifc_export import gen_ifc


def check():
    base = l_polygon([8720,9095,4860,2410,3860,6685])
    assert np.allclose(transform_polygon(base,4),base)
    assert np.allclose(transform_polygon(transform_polygon(base,mirrored=True),mirrored=True),base)
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    baseline = None
    for mirror in (False,True):
        for turns in range(4):
            pts = transform_polygon(base,turns,mirror)
            assert np.allclose(wall_lengths(pts),wall_lengths(base))
            doors = [("Fryserom enkel 1000×2100 mm",1,i,.35) for i in (0,2,4)]
            inp = ProjectInput("Rotasjon og speiling","","","","1:50","Fryserom",
                               "PIR 150 mm",pts,2.5,1.1,doors,[])
            result = beregn_prosjekt(inp,pris_override={f"dor_{doors[0][0]}":20000})
            if baseline is None:
                baseline = result["tot_pris"]
            assert result["tot_pris"] == baseline
            fig3 = tegn_3d_modell(inp)
            door_traces = [t for t in fig3.data if t.name.startswith("Dør –")]
            model = ifcopenshell.file.from_string(gen_ifc(pts,2.5,"Test",inp.panel_key,doors,inp.rom_type).decode())
            for entry, trace, door in zip(doors,door_traces,model.by_type("IfcDoor")):
                i = entry[2]
                a,b = np.array(pts[i]),np.array(pts[(i+1)%6])
                direction = (b-a)/np.linalg.norm(b-a)
                expected = a + direction*.85
                assert np.allclose([np.mean(trace.x),np.mean(trace.y)],expected)
                shape = ifcopenshell.geom.create_shape(settings,door)
                vertices = np.array(shape.geometry.verts).reshape(-1,3)
                center = (vertices.min(axis=0)+vertices.max(axis=0))/2
                inward = polygon_winding(pts)*np.array([-direction[1],direction[0]])
                assert np.allclose(center[:2],expected-inward*.075)
            assert len(door_traces) == len(model.by_type("IfcDoor")) == 3
            for element in list(model.by_type("IfcWall"))+list(model.by_type("IfcBuildingElementProxy")):
                shape = ifcopenshell.geom.create_shape(settings,element)
                assert shape.geometry.verts
            plan = tegn_plantegning(inp,result)
            if mirror and turns == 1:
                out = Path(__file__).parent / "qa"
                out.mkdir(exist_ok=True)
                plan.savefig(out/"l-rotated-mirrored.png",dpi=110)
            plt.close("all")
    print("PASS: 8 transforms; dimensions, price, 3D and IFC door positions, wall/channel geometry")


if __name__ == "__main__":
    check()
