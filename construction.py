"""Shared dimensions in metres. H is wall-panel height, not clear room height."""
CHANNEL_HEIGHT = 0.050
CHANNEL_FLANGE = 0.0006
FLOOR_PIR = 0.100
FLOOR_BOARD = 0.012
BATTEN_HEIGHT = 0.022


def wall_polygon(pts, index, thickness, excluded_walls=()):
    """Wall outside the clear-room polygon; square butt joints at 90 degrees.

    The following wall owns a convex corner. At a concave corner the
    preceding wall stops short. Oblique corners retain their mitred joint.
    Omitted neighbours never extend a free wall end.
    """
    import numpy as np
    from geometry import polygon_winding
    p = np.asarray(pts, dtype=float)
    n = len(p)
    a, b = p[index], p[(index+1)%n]
    direction = (b-a)/np.linalg.norm(b-a)
    inward = polygon_winding(p)*np.array([-direction[1], direction[0]])
    outer = np.asarray(floor_outline(pts, thickness))
    ai, bi = a.copy(), b.copy()
    ao, bo = a-inward*thickness, b-inward*thickness
    for at_start, neighbour in ((True, (index-1)%n), (False, (index+1)%n)):
        if neighbour in excluded_walls:
            continue
        v = (a-p[neighbour]) if at_start else (p[(index+2)%n]-b)
        v /= np.linalg.norm(v)
        u, w = (v, direction) if at_start else (direction, v)
        turn = polygon_winding(p)*(u[0]*w[1]-u[1]*w[0])
        if abs(np.dot(u,w)) < 1e-8:
            if at_start and turn > 0:
                ai -= direction*thickness
                ao -= direction*thickness
            elif not at_start and turn < 0:
                bi -= direction*thickness
                bo -= direction*thickness
        elif at_start:
            ao = outer[index]
        else:
            bo = outer[(index+1)%n]
    return np.array([ai, bi, bo, ao])


def wall_span(pts, index, thickness, excluded_walls=()):
    import numpy as np
    a, b = np.asarray(pts[index]), np.asarray(pts[(index+1)%len(pts)])
    direction = (b-a)/np.linalg.norm(b-a)
    distances = (wall_polygon(pts,index,thickness,excluded_walls)-a) @ direction
    return float(distances.min()), float(distances.max())


def wall_outer_face_span(pts, index, thickness, excluded_walls=()):
    """Exterior face coverage includes the end face of the adjoining corner panel."""
    import numpy as np
    a,b=np.asarray(pts[index]),np.asarray(pts[(index+1)%len(pts)])
    direction=(b-a)/np.linalg.norm(b-a)
    outline=np.asarray(floor_outline(pts,thickness))
    start=a if (index-1)%len(pts) in excluded_walls else outline[index]
    end=b if (index+1)%len(pts) in excluded_walls else outline[(index+1)%len(pts)]
    return float((start-a)@direction),float((end-a)@direction)


def wall_panel_layout(pts, width_mm, thickness, excluded_walls=()):
    """One physical panel layout shared by cuts, drawings and 3D seams.

    Start/end are measured from the unchanged clear-room corner, so door
    offsets remain stable even when a panel extends past that corner.
    """
    rows, number, rest = [], 1, 0
    for index in range(len(pts)):
        if index in excluded_walls:
            rest = 0
            continue
        lo, hi = wall_span(pts,index,thickness,excluded_walls)
        cursor, end = round(lo*1000), round(hi*1000)
        while cursor < end:
            from_rest = rest > 0
            width = min(rest if from_rest else width_mm, end-cursor)
            kind = "Rest fra forrige" if from_rest else "Hel" if width == width_mm else "Kapp (videreføres)"
            rows.append(dict(wall=index, name=f"V{number}", start_mm=cursor,
                             width_mm=width, kind=kind))
            number += 1
            cursor += width
            rest = max(rest-width,0) if from_rest else width_mm-width
    return rows


def wall_panel_polygon(pts, index, start_m, end_m, thickness, excluded_walls=()):
    """Clip the common wall footprint to one panel interval."""
    import numpy as np
    a, b = np.asarray(pts[index]), np.asarray(pts[(index+1)%len(pts)])
    direction = (b-a)/np.linalg.norm(b-a)
    polygon = list(wall_polygon(pts,index,thickness,excluded_walls))
    for bound, sign in ((start_m,1),(end_m,-1)):
        clipped = []
        for u,v in zip(polygon,polygon[1:]+polygon[:1]):
            du, dv = sign*((u-a)@direction-bound), sign*((v-a)@direction-bound)
            if du >= -1e-9:
                clipped.append(u)
            if (du < 0 < dv) or (dv < 0 < du):
                clipped.append(u+(v-u)*du/(du-dv))
        polygon = clipped
    return np.asarray(polygon)


def floor_depth(room_type):
    return FLOOR_BOARD if room_type == "Fryserom" else 0.0


def wall_base(room_type, panel_key="PIR 100 mm"):
    from database import PANEL_DB
    return BATTEN_HEIGHT + PANEL_DB[panel_key]["t"]/1000 if room_type == "Fryserom" else 0.0


def finished_floor(room_type, panel_key="PIR 100 mm"):
    return wall_base(room_type, panel_key) + floor_depth(room_type)


def floor_outline(pts, thickness):
    """Panel floor extends to outside wall faces; input polygon is clear inside."""
    import numpy as np
    from geometry import polygon_winding
    a = np.asarray(pts, dtype=float)
    winding = polygon_winding(pts)
    result = []
    for i,p in enumerate(a):
        u = p-a[i-1]; v = a[(i+1)%len(a)]-p
        u /= np.linalg.norm(u); v /= np.linalg.norm(v)
        n = winding*np.array([-u[1],u[0]])
        m = winding*np.array([-v[1],v[0]])
        matrix = np.array([n,m])
        shift = np.linalg.solve(matrix,np.array([-thickness,-thickness])) if abs(np.linalg.det(matrix))>1e-9 else -n*thickness
        result.append(tuple(p+shift))
    return result


def door_keys(room_type, doors):
    return [key for key in doors if ("Fryserom" in key) == (room_type == "Fryserom")]


def roof_outline(pts, thickness, room_type):
    """Freezer roof and floor use the same outside-wall footprint."""
    return floor_outline(pts, thickness) if room_type == "Fryserom" else pts


def fixing_screw_count(pts, height, room_type, thickness, excluded_walls=()):
    """Two rows, max 400 mm spacing, with a fixing at each end of each trim."""
    import math
    from geometry import beslag_beregning, wall_lengths
    clear = height - floor_depth(room_type)
    bb = beslag_beregning(pts, height, excluded_walls, thickness, clear,
                         floor_angles=room_type == "Fryserom")
    count = 2 * (bb["n_inn"] * (math.ceil(clear/.4 - 1e-10) + 1)
                 + bb["n_ut"] * (math.ceil(height/.4 - 1e-10) + 1))
    if room_type == "Fryserom":
        for outline in (pts, floor_outline(pts, thickness)):
            count += 2 * sum(math.ceil(length/.4 - 1e-10) + 1
                             for i, length in enumerate(wall_lengths(outline))
                             if i not in excluded_walls)
    return count
