from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import uuid
from typing import Iterable

import numpy as np

from database import PANEL_DB, DOR_DB
from panel_engine import generate_roof_floor_panels


def ifc_guid() -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
    num = int.from_bytes(uuid.uuid4().bytes, "big")
    out = []
    for _ in range(22):
        out.append(chars[num % 64])
        num //= 64
    return "".join(reversed(out))


def _ifc_text(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _refs(ids: Iterable[int]) -> str:
    return "(" + ",".join(f"#{int(i)}" for i in ids) + ")"


def gen_ifc(
    pts_m,
    h: float,
    navn: str,
    panel_key: str,
    dorer=None,
    rom_type: str = "Kjølerom",
    panelbredde_m: float = 1.10,
    apninger=None,          # [(wall_idx, offset_m, width_m, height_m, sill_m, label), ...]
) -> bytes:
    """
    IFC2X3-eksport med korrekte vegger, U-kanal, tak/gulvpaneler og booleanske åpninger.

    Vegger:
    - Plassert langs polygon-kanten
    - Tykkelse utover fra rom-polygonen (innvendig flate = polygon-kanten)
    - Korrekt hjørnegeometri via miter-cut av profilen

    Åpninger:
    - Dører: fra DOR_DB, plassert på riktig vegg med offset
    - Klassfronter/åpninger: fra apninger-lista med valgfri sill-høyde
    - Implementert som IfcOpeningElement + IfcRelVoidsElement (booleansk hull)
    """
    pan     = PANEL_DB[panel_key]
    tk      = pan["t"] / 1000.0          # veggtykkelse
    roof_tk = tk
    UC_h    = 0.080                       # U-kanal høyde
    IS_FRYS = "Fryserom" in rom_type
    floor_tk = 0.10 if IS_FRYS else 0.0
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    lines: list[str] = []
    counter = 0

    def E(entity: str, *args) -> int:
        nonlocal counter
        counter += 1
        lines.append(f"#{counter}={entity}({', '.join(str(a) for a in args)});")
        return counter

    # ── Geometri-hjelpere ─────────────────────────────────────────────────────

    def p2(x: float, y: float) -> int:
        return E("IFCCARTESIANPOINT", f"({float(x):.6f},{float(y):.6f})")

    def p3(x: float, y: float, z: float) -> int:
        return E("IFCCARTESIANPOINT", f"({float(x):.6f},{float(y):.6f},{float(z):.6f})")

    def d3(x: float, y: float, z: float) -> int:
        return E("IFCDIRECTION", f"({float(x):.6f},{float(y):.6f},{float(z):.6f})")

    def axis3d(x=0., y=0., z=0., axis=(0,0,1), ref=(1,0,0)) -> int:
        return E("IFCAXIS2PLACEMENT3D",
                 f"#{p3(x, y, z)}", f"#{d3(*axis)}", f"#{d3(*ref)}")

    def placement(rel="$", x=0., y=0., z=0., axis=(0,0,1), ref=(1,0,0)) -> int:
        return E("IFCLOCALPLACEMENT", rel, f"#{axis3d(x, y, z, axis, ref)}")

    def rect_profile_2d(width: float, height: float) -> int:
        """Rektangel-profil: (0,0) → (width, height) i lokal XY."""
        ids = [p2(0,0), p2(width,0), p2(width,height), p2(0,height)]
        poly = E("IFCPOLYLINE", _refs(ids + [ids[0]]))
        return E("IFCARBITRARYCLOSEDPROFILEDEF", ".AREA.", "$", f"#{poly}")

    def polygon_profile_2d(poly_pts: np.ndarray) -> int:
        ids = [p2(float(p[0]), float(p[1])) for p in poly_pts]
        poly = E("IFCPOLYLINE", _refs(ids + [ids[0]]))
        return E("IFCARBITRARYCLOSEDPROFILEDEF", ".AREA.", "$", f"#{poly}")

    def extrude(profile_id: int, depth: float,
                dir_x=0., dir_y=0., dir_z=1.) -> int:
        """Extrude profil i retning (dir_x, dir_y, dir_z)."""
        solid = E("IFCEXTRUDEDAREASOLID",
                  f"#{profile_id}", "$",
                  f"#{d3(dir_x, dir_y, dir_z)}",
                  f"{float(depth):.6f}")
        rep = E("IFCSHAPEREPRESENTATION",
                f"#{context}", _ifc_text("Body"), _ifc_text("SweptSolid"),
                _refs([solid]))
        return E("IFCPRODUCTDEFINITIONSHAPE", "$", "$", _refs([rep]))

    def assign_mat(pid: int, mid: int):
        E("IFCRELASSOCIATESMATERIAL",
          _ifc_text(ifc_guid()), "$", "$", "$", _refs([pid]), f"#{mid}")

    # ── IFC-kontekst ──────────────────────────────────────────────────────────

    header = (
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_DESCRIPTION(('Stramo kjøle-/fryserom'),'2;1');\n"
        f"FILE_NAME({_ifc_text(navn + '.ifc')},{_ifc_text(now)},"
        f"('Stramo'),('Stramo'),'Stramo app','Stramo','');\n"
        "FILE_SCHEMA(('IFC2X3'));\n"
        "ENDSEC;\n"
        "DATA;\n"
    )

    context = E("IFCGEOMETRICREPRESENTATIONCONTEXT",
                _ifc_text("Model"), _ifc_text("Model"), 3, "1.0E-5",
                f"#{axis3d()}", "$")
    lu = E("IFCSIUNIT", "$", ".LENGTHUNIT.", "$", ".METRE.")
    au = E("IFCSIUNIT", "$", ".AREAUNIT.", "$", ".SQUARE_METRE.")
    vu = E("IFCSIUNIT", "$", ".VOLUMEUNIT.", "$", ".CUBIC_METRE.")
    units = E("IFCUNITASSIGNMENT", _refs([lu, au, vu]))

    project   = E("IFCPROJECT", _ifc_text(ifc_guid()), "$", _ifc_text(navn),
                  "$","$","$","$", _refs([context]), f"#{units}")
    site_pl   = placement()
    site      = E("IFCSITE", _ifc_text(ifc_guid()), "$", _ifc_text("Tomt"),
                  "$","$", f"#{site_pl}","$","$",".ELEMENT.","$","$","$","$","$")
    bldg_pl   = placement()
    building  = E("IFCBUILDING", _ifc_text(ifc_guid()), "$", _ifc_text(navn),
                  "$","$", f"#{bldg_pl}","$","$",".ELEMENT.","$","$","$")
    storey_pl = placement()
    storey    = E("IFCBUILDINGSTOREY", _ifc_text(ifc_guid()), "$",
                  _ifc_text("Etasje 1"), "$","$", f"#{storey_pl}","$","$",
                  ".ELEMENT.","0.")
    E("IFCRELAGGREGATES", _ifc_text(ifc_guid()),"$","$","$",
      f"#{project}", _refs([site]))
    E("IFCRELAGGREGATES", _ifc_text(ifc_guid()),"$","$","$",
      f"#{site}", _refs([building]))
    E("IFCRELAGGREGATES", _ifc_text(ifc_guid()),"$","$","$",
      f"#{building}", _refs([storey]))

    mat_panel = E("IFCMATERIAL", _ifc_text(f"Isolasjonspanel {pan['label']}"))
    mat_floor = E("IFCMATERIAL", _ifc_text("Gulvplate"))
    mat_door  = E("IFCMATERIAL", _ifc_text("Isolert kjøleromsdør"))
    mat_glass = E("IFCMATERIAL", _ifc_text("Klassfrontåpning"))

    products: list[int] = []
    pts_a = np.array(pts_m, dtype=float)
    nn    = len(pts_a)

    # ── Normaliser polygon CCW ─────────────────────────────────────────────────
    def _signed_area(p):
        n = len(p)
        return 0.5 * sum(
            p[i][0]*p[(i+1)%n][1] - p[(i+1)%n][0]*p[i][1]
            for i in range(n))
    if _signed_area(pts_a) < 0:
        pts_a = pts_a[::-1]

    # ── Vegger ────────────────────────────────────────────────────────────────
    # Profil i lokal XZ-plan av veggen:
    #   X_local = langs veggen (0 → length)
    #   Y_local = venstre perp = innover i rommet (positiv Y = inn)
    #   Z_local = opp
    # Panelet: X 0→length, Y 0→-tk (fra indre flate utover)
    # Vegg-plassering: origin = P1 i verdenskoordinater, ref = veggretning
    #
    # For å lukke hjørner bruker vi miter-teknikk:
    # Veggen strekkes et halvt tykkelse inn i nabohjørnene.

    wall_ids: list[int] = []   # for å koble åpninger til riktig vegg

    for i in range(nn):
        p1v = pts_a[i]
        p2v = pts_a[(i + 1) % nn]
        seg  = p2v - p1v
        L    = float(np.linalg.norm(seg))
        if L < 1e-6:
            wall_ids.append(0)
            continue

        ca, sa = seg[0]/L, seg[1]/L   # veggretning (lokal X)
        # Lokal Y (venstre perp, innover for CCW): (-sa, ca)
        # Lokal Y utover (ekstern side): (sa, -ca)

        # Profil i lokal XY (2D, X=langs vegg, Y=tykkelse):
        # Y=0 er innvendig flate, Y=-tk er utvendig flate.
        # Utvid X med tk i hver ende for lukkede hjørner.
        ext = tk
        corners_2d = [
            p2(-ext,    0.0),
            p2(L+ext,   0.0),
            p2(L+ext,  -tk),
            p2(-ext,   -tk),
        ]
        poly2d = E("IFCPOLYLINE", _refs(corners_2d + [corners_2d[0]]))
        prof   = E("IFCARBITRARYCLOSEDPROFILEDEF", ".AREA.", "$", f"#{poly2d}")

        # Extruder i Z (opp) med høyde h (fri vegg = uten UK og tak)
        solid = E("IFCEXTRUDEDAREASOLID",
                  f"#{prof}", "$", f"#{d3(0,0,1)}", f"{h:.6f}")
        rep   = E("IFCSHAPEREPRESENTATION",
                  f"#{context}", _ifc_text("Body"), _ifc_text("SweptSolid"),
                  _refs([solid]))
        shape = E("IFCPRODUCTDEFINITIONSHAPE", "$", "$", _refs([rep]))

        # Plassering: origin = P1, X_local = veggretning, Z_local = opp
        # z = UC_h slik at vegg starter på topp U-kanal
        w_pl   = placement(f"#{storey_pl}",
                           float(p1v[0]), float(p1v[1]), UC_h,
                           axis=(0,0,1), ref=(float(ca), float(sa), 0))
        wall_e = E("IFCWALL", _ifc_text(ifc_guid()), "$",
                   _ifc_text(f"Vegg {i+1}"), "$", "$",
                   f"#{w_pl}", f"#{shape}", "$")
        assign_mat(wall_e, mat_panel)
        products.append(wall_e)
        wall_ids.append(wall_e)

    # ── Åpnings-hjelpefunksjon ────────────────────────────────────────────────
    # Hvert hull er et IfcOpeningElement plassert i verdenskoordinater.
    # offset_m = avstand fra P_i langs veggen.
    # sill_m   = høyde fra gulvnivå til underkant åpning.

    def _add_opening(wall_entity: int, wall_idx: int,
                     offset_m: float, width_m: float, height_m: float,
                     sill_m: float, label: str, is_door: bool = True):
        p1v = pts_a[wall_idx]
        p2v = pts_a[(wall_idx + 1) % nn]
        seg  = p2v - p1v
        L    = float(np.linalg.norm(seg))
        if L < 1e-6 or offset_m + width_m > L + 0.01:
            return None, None

        ca, sa = seg[0]/L, seg[1]/L
        # Lokal Y = venstre perp = inn i rom: (-sa, ca)
        # Utover (eksternt) = (sa, -ca), dvs Y_lokal = -1 → utover

        # Åpnings-opprinnelse i verdenskoordinater:
        # Horisontal: P1 + offset langs vegg
        # Lateral: flytt ut til ekstern flate = Y_lokal = -tk
        # Vertikal: UK = UC_h + sill_m

        # Åpningens lokal system: X = veggretning, Y = utover, Z = opp
        ox = float(p1v[0]) + ca * offset_m + sa * tk    # X_world = P1 + offset·dir + tk·outward_x
        oy = float(p1v[1]) + sa * offset_m + (-ca) * tk # Y_world
        oz = UC_h + sill_m

        # Outward normal i verdenskoordinater: (sa, -ca, 0) for CCW polygon
        # = lokal Y for åpningsplacements ref=(ca,sa,0) → outward = (-left_perp)
        # Siden local Y_wall = (-sa, ca) innover → utover = (sa, -ca)
        # Vi vil ekstruder åpningssolidet gjennom veggen: retning = innover = (-sa, ca)
        nx, ny = float(-sa), float(ca)  # innover, gjennom veggen

        # Åpnings-profil i lokal XZ-planet (width × height):
        # X_local = veggretning, Z_local = opp
        # Vi ekstruder i lokal Y (= verdenskoordinat innover)
        prof = rect_profile_2d(width_m, height_m)
        solid = E("IFCEXTRUDEDAREASOLID",
                  f"#{prof}", "$",
                  f"#{d3(0., 1., 0.)}",  # extrude in local Y = gjennom veggen
                  f"{tk * 2:.6f}")        # litt ekstra for sikker kapping
        rep   = E("IFCSHAPEREPRESENTATION",
                  f"#{context}", _ifc_text("Body"), _ifc_text("SweptSolid"),
                  _refs([solid]))
        o_shape = E("IFCPRODUCTDEFINITIONSHAPE", "$", "$", _refs([rep]))

        # Plassering av åpning: origin = eksternt hjørne,
        # X = veggretning, Y = innover (= gjennom veggen)
        # IFCAXIS2PLACEMENT3D: axis=Z_world, ref=X_local
        o_ax = E("IFCAXIS2PLACEMENT3D",
                 f"#{p3(ox, oy, oz)}",
                 f"#{d3(0., 0., 1.)}",
                 f"#{d3(float(ca), float(sa), 0.)}")
        o_pl = E("IFCLOCALPLACEMENT", f"#{storey_pl}", f"#{o_ax}")

        opening = E("IFCOPENINGELEMENT",
                    _ifc_text(ifc_guid()), "$",
                    _ifc_text(label), "$", "$",
                    f"#{o_pl}", f"#{o_shape}", "$")

        # Koble åpningen til veggen
        E("IFCRELVOIDSELEMENT",
          _ifc_text(ifc_guid()), "$", "$", "$",
          f"#{wall_entity}", f"#{opening}")

        return opening, (o_pl, o_shape, ox, oy, oz, ca, sa, width_m, height_m)

    # ── Dører ─────────────────────────────────────────────────────────────────
    if dorer:
        for entry in dorer:
            dk = entry[0]; ant = int(entry[1])
            wall_idx  = int(entry[2]) if len(entry) > 2 else 0
            offset_m  = float(entry[3]) if len(entry) > 3 else 0.35

            if wall_idx >= nn or wall_ids[wall_idx] == 0:
                continue

            d_db = DOR_DB[dk]
            dw   = d_db["bw"] / 1000.0
            dh   = d_db["bh"] / 1000.0

            p1v = pts_a[wall_idx]
            p2v = pts_a[(wall_idx + 1) % nn]
            L   = float(np.linalg.norm(p2v - p1v))
            seg = p2v - p1v
            ca_w, sa_w = seg[0]/L, seg[1]/L

            cur = offset_m
            for j in range(max(1, ant)):
                if cur + dw > L:
                    break
                opening, geo = _add_opening(
                    wall_ids[wall_idx], wall_idx,
                    cur, dw, dh, 0.0,
                    f"Dør {dk} – {j+1}", is_door=True)

                if opening and geo:
                    (o_pl, _, ox, oy, oz, ca_d, sa_d, dw2, dh2) = geo
                    # IfcDoor inne i åpningen
                    dp = rect_profile_2d(dw2, dh2)
                    ds = E("IFCEXTRUDEDAREASOLID",
                           f"#{dp}", "$", f"#{d3(0.,1.,0.)}",
                           f"{tk:.6f}")
                    dr_rep  = E("IFCSHAPEREPRESENTATION",
                                f"#{context}", _ifc_text("Body"),
                                _ifc_text("SweptSolid"), _refs([ds]))
                    dr_shp  = E("IFCPRODUCTDEFINITIONSHAPE",
                                "$","$", _refs([dr_rep]))
                    dr_ax   = E("IFCAXIS2PLACEMENT3D",
                                f"#{p3(ox, oy, oz)}",
                                f"#{d3(0.,0.,1.)}",
                                f"#{d3(float(ca_d), float(sa_d), 0.)}")
                    dr_pl   = E("IFCLOCALPLACEMENT",
                                f"#{storey_pl}", f"#{dr_ax}")
                    door_e  = E("IFCDOOR",
                                _ifc_text(ifc_guid()), "$",
                                _ifc_text(d_db["label"]), "$", "$",
                                f"#{dr_pl}", f"#{dr_shp}", "$",
                                f"{dh2:.3f}", f"{dw2:.3f}")
                    assign_mat(door_e, mat_door)
                    E("IFCRELFILLSELEMENT",
                      _ifc_text(ifc_guid()),"$","$","$",
                      f"#{opening}", f"#{door_e}")
                    products.append(door_e)

                cur += dw + 0.25

    # ── Klassfronter / tilpassede åpninger ────────────────────────────────────
    if apninger:
        for ap in apninger:
            wall_idx, offset_m, width_m, height_m, sill_m, label = ap
            if wall_idx >= nn or wall_ids[wall_idx] == 0:
                continue
            opening, geo = _add_opening(
                wall_ids[wall_idx], wall_idx,
                offset_m, width_m, height_m, sill_m,
                label, is_door=False)
            if opening and geo:
                (o_pl, _, ox, oy, oz, ca_d, sa_d, w2, h2) = geo
                # IfcWindow for klassfronter
                wp = rect_profile_2d(w2, h2)
                ws = E("IFCEXTRUDEDAREASOLID",
                       f"#{wp}", "$", f"#{d3(0.,1.,0.)}",
                       f"{tk:.6f}")
                wr  = E("IFCSHAPEREPRESENTATION",
                        f"#{context}", _ifc_text("Body"),
                        _ifc_text("SweptSolid"), _refs([ws]))
                wsh = E("IFCPRODUCTDEFINITIONSHAPE","$","$",_refs([wr]))
                wax = E("IFCAXIS2PLACEMENT3D",
                        f"#{p3(ox, oy, oz)}",
                        f"#{d3(0.,0.,1.)}",
                        f"#{d3(float(ca_d), float(sa_d), 0.)}")
                wpl = E("IFCLOCALPLACEMENT", f"#{storey_pl}", f"#{wax}")
                win = E("IFCWINDOW",
                        _ifc_text(ifc_guid()),"$",
                        _ifc_text(label),"$","$",
                        f"#{wpl}", f"#{wsh}","$",
                        f"{h2:.3f}", f"{w2:.3f}")
                assign_mat(win, mat_glass)
                E("IFCRELFILLSELEMENT",
                  _ifc_text(ifc_guid()),"$","$","$",
                  f"#{opening}", f"#{win}")
                products.append(win)

    # ── Gulv ──────────────────────────────────────────────────────────────────
    floor_prof  = polygon_profile_2d(pts_a)
    floor_solid = E("IFCEXTRUDEDAREASOLID",
                    f"#{floor_prof}", "$", f"#{d3(0,0,1)}", "0.005000")
    floor_rep   = E("IFCSHAPEREPRESENTATION",
                    f"#{context}", _ifc_text("Body"), _ifc_text("SweptSolid"),
                    _refs([floor_solid]))
    floor_shape = E("IFCPRODUCTDEFINITIONSHAPE","$","$",_refs([floor_rep]))
    floor_pl    = placement(f"#{storey_pl}", 0, 0, UC_h - 0.005)
    floor_e     = E("IFCSLAB", _ifc_text(ifc_guid()),"$",
                    _ifc_text("Gulvflate"),"$","$",
                    f"#{floor_pl}", f"#{floor_shape}","$",".FLOOR.")
    assign_mat(floor_e, mat_floor)
    products.append(floor_e)

    # ── Takpaneler ────────────────────────────────────────────────────────────
    pw_mm  = max(1, int(round(panelbredde_m * 1000)))
    z_roof = UC_h + h   # underkant tak = topp vegg

    try:
        roof_panels = generate_roof_floor_panels(
            pts_a.tolist(), pw_mm, prefix="T", label="Tak", cut_position="end")
    except Exception:
        roof_panels = []

    if roof_panels:
        for p in roof_panels:
            pa    = np.array(p.polygon, dtype=float)
            rprof = polygon_profile_2d(pa)
            rs    = E("IFCEXTRUDEDAREASOLID",
                      f"#{rprof}", "$", f"#{d3(0,0,1)}", f"{roof_tk:.6f}")
            rrep  = E("IFCSHAPEREPRESENTATION",
                      f"#{context}", _ifc_text("Body"), _ifc_text("SweptSolid"),
                      _refs([rs]))
            rshp  = E("IFCPRODUCTDEFINITIONSHAPE","$","$",_refs([rrep]))
            rpl   = placement(f"#{storey_pl}", 0, 0, z_roof)
            roof  = E("IFCSLAB", _ifc_text(ifc_guid()),"$",
                      _ifc_text(f"{p.name} – {p.kind}"),"$",
                      _ifc_text(f"{p.width_mm}×{p.span_mm} mm"),
                      f"#{rpl}", f"#{rshp}","$",".ROOF.")
            assign_mat(roof, mat_panel)
            products.append(roof)
    else:
        rprof = polygon_profile_2d(pts_a)
        rs    = E("IFCEXTRUDEDAREASOLID",
                  f"#{rprof}", "$", f"#{d3(0,0,1)}", f"{roof_tk:.6f}")
        rrep  = E("IFCSHAPEREPRESENTATION",
                  f"#{context}", _ifc_text("Body"), _ifc_text("SweptSolid"),
                  _refs([rs]))
        rshp  = E("IFCPRODUCTDEFINITIONSHAPE","$","$",_refs([rrep]))
        rpl   = placement(f"#{storey_pl}", 0, 0, z_roof)
        roof  = E("IFCSLAB", _ifc_text(ifc_guid()),"$",
                  _ifc_text("Tak"),"$","$",
                  f"#{rpl}", f"#{rshp}","$",".ROOF.")
        assign_mat(roof, mat_panel)
        products.append(roof)

    # ── Gulvpaneler (fryserom) ────────────────────────────────────────────────
    if IS_FRYS:
        try:
            floor_panels = generate_roof_floor_panels(
                pts_a.tolist(), pw_mm, prefix="G", label="Gulv PIR", cut_position="end")
        except Exception:
            floor_panels = []
        for p in floor_panels:
            pa   = np.array(p.polygon, dtype=float)
            gp   = polygon_profile_2d(pa)
            gs   = E("IFCEXTRUDEDAREASOLID",
                     f"#{gp}", "$", f"#{d3(0,0,1)}", "0.100000")
            gr   = E("IFCSHAPEREPRESENTATION",
                     f"#{context}", _ifc_text("Body"), _ifc_text("SweptSolid"),
                     _refs([gs]))
            gsh  = E("IFCPRODUCTDEFINITIONSHAPE","$","$",_refs([gr]))
            gpl  = placement(f"#{storey_pl}", 0, 0, UC_h)
            ge   = E("IFCSLAB", _ifc_text(ifc_guid()),"$",
                     _ifc_text(f"{p.name} – {p.kind}"),"$",
                     _ifc_text(f"{p.width_mm}×{p.span_mm} mm"),
                     f"#{gpl}", f"#{gsh}","$",".FLOOR.")
            assign_mat(ge, mat_panel)
            products.append(ge)

    E("IFCRELCONTAINEDINSPATIALSTRUCTURE",
      _ifc_text(ifc_guid()),"$","$","$",
      _refs(products), f"#{storey}")

    return (header + "\n".join(lines) + "\nENDSEC;\nEND-ISO-10303-21;\n").encode("utf-8")


@dataclass
class IFCExporter:
    pts_m: list[tuple[float, float]]
    h: float
    navn: str
    panel_key: str
    dorer: list | None = None
    rom_type: str = "Kjølerom"
    apninger: list | None = None

    def export(self) -> bytes:
        return gen_ifc(self.pts_m, self.h, self.navn, self.panel_key,
                       self.dorer, self.rom_type, apninger=self.apninger)
