from __future__ import annotations
import math
from typing import Sequence, Tuple
import numpy as np

Point = Tuple[float, float]
EPS = 1e-6


def transform_polygon(pts, quarter_turns=0, mirrored=False):
    """Rigid transform preserving corner/wall indices and distances."""
    result = []
    for x, y in pts:
        if mirrored:
            x = -x
        for _ in range(quarter_turns % 4):
            x, y = y, -x
        result.append((x, y))
    xmin = min(x for x,y in result)
    ymin = min(y for x,y in result)
    return [(x-xmin, y-ymin) for x,y in result]


def polygon_winding(pts):
    signed = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(pts, list(pts[1:])+[pts[0]]))
    return 1 if signed > 0 else -1


def l_polygon(sides):
    """Infer the concave corner from six consecutive lengths; V1 runs right.

    A simple orthogonal L has five left turns and one right turn (CCW).
    Try each location of that right turn without changing any input length.
    """
    if len(sides) != 6 or any(not math.isfinite(v) or v <= 0 for v in sides):
        raise ValueError("Oppgi seks positive sidelengder.")
    for concave_corner in range(6):
        points = [(0.0, 0.0)]
        dx, dy = 1, 0
        for i, length in enumerate(sides):
            x, y = points[-1]
            points.append((x + dx*length, y + dy*length))
            if (i+1) % 6 == concave_corner:
                dx, dy = dy, -dx
            else:
                dx, dy = -dy, dx
        if abs(points[-1][0]) > EPS or abs(points[-1][1]) > EPS:
            continue
        points = points[:-1]
        # Non-neighbouring axis-aligned segments must not cross or touch.
        intersects = False
        for i in range(6):
            a, b = points[i], points[(i+1)%6]
            for j in range(i+2,6):
                if i == 0 and j == 5:
                    continue
                c, d = points[j], points[(j+1)%6]
                if (max(min(a[0],b[0]), min(c[0],d[0])) <= min(max(a[0],b[0]),max(c[0],d[0])) + EPS
                    and max(min(a[1],b[1]),min(c[1],d[1])) <= min(max(a[1],b[1]),max(c[1],d[1])) + EPS):
                    intersects = True
        if not intersects:
            xmin = min(x for x,y in points)
            ymin = min(y for x,y in points)
            return [((x-xmin)/1000, (y-ymin)/1000) for x,y in points]
    horizontal = sides[::2]
    vertical = sides[1::2]
    hx = abs(2*max(horizontal)-sum(horizontal))
    vy = abs(2*max(vertical)-sum(vertical))
    raise ValueError(
        f"Målene danner ikke en lukket L-form i denne rekkefølgen. "
        f"Avvik vannrett (V1/V3/V5): {hx:g} mm; loddrett (V2/V4/V6): {vy:g} mm. "
        "Den lengste siden i hver gruppe må være summen av de to andre. "
        "Ved null avvik: kontroller rekkefølgen på sidene. Ingen mål er endret."
    )


def door_dimensions(wall_length, offset, width):
    """Metres: start corner to near edge/centre, far edge/centre to end corner."""
    if width <= 0 or offset < 0 or offset + width > wall_length + EPS:
        raise ValueError("Døren må ligge innenfor valgt vegg.")
    return offset, offset + width/2, max(0, wall_length-offset-width), wall_length-offset-width/2

def mm_to_m(value_mm: float) -> float:
    """Konverterer millimeter til meter."""
    return value_mm / 1000.0

def m_to_mm(value_m: float) -> int:
    """Konverterer meter til millimeter, avrundet til nærmeste heltall."""
    return int(round(value_m * 1000))

def validate_polygon(pts: Sequence[Point]) -> None:
    """Require a finite, simple polygon; adjacent edges may share one endpoint."""
    if len(pts) < 3:
        raise ValueError("Polygon må ha minst 3 punkter.")
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in pts):
        raise ValueError("Hvert hjørne må ha to endelige koordinater.")
    rounded = {(round(float(x), 6), round(float(y), 6)) for x, y in pts}
    if len(rounded) != len(pts):
        raise ValueError("Polygonet inneholder dupliserte hjørnepunkter.")
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])

    def on_segment(a, b, p):
        return (abs(cross(a, b, p)) <= EPS
                and min(a[0], b[0])-EPS <= p[0] <= max(a[0], b[0])+EPS
                and min(a[1], b[1])-EPS <= p[1] <= max(a[1], b[1])+EPS)

    n = len(pts)
    for i in range(n):
        a, b, c = pts[i], pts[(i+1) % n], pts[(i+2) % n]
        if math.dist(a, b) <= EPS:
            raise ValueError("En vegg har null lengde.")
        if abs(cross(a, b, c)) <= EPS and sum((a[k]-b[k])*(c[k]-b[k]) for k in (0, 1)) > EPS:
            raise ValueError("Nabovegger overlapper hverandre.")
        for j in range(i+2, n):
            if i == 0 and j == n-1:
                continue
            c, d = pts[j], pts[(j+1) % n]
            ab_c, ab_d, cd_a, cd_b = cross(a,b,c), cross(a,b,d), cross(c,d,a), cross(c,d,b)
            crosses = ((ab_c > EPS and ab_d < -EPS or ab_c < -EPS and ab_d > EPS)
                       and (cd_a > EPS and cd_b < -EPS or cd_a < -EPS and cd_b > EPS))
            if crosses or any((on_segment(a,b,c), on_segment(a,b,d), on_segment(c,d,a), on_segment(c,d,b))):
                raise ValueError("Polygonets vegger krysser eller berører hverandre. Kontroller hjørnenes rekkefølge.")
    if poly_area_raw(pts) <= EPS:
        raise ValueError("Polygonet har null eller negativt areal.")


def validate_wall_openings(pts, clear_height, doors, openings=()):
    """Validate opening rectangles in each wall, measured from finished floor.

    Legacy two-field doors carry quantities only, so their placement cannot be
    checked. The editor and project files supply the full wall/offset fields.
    """
    from database import DOR_DB
    lengths = wall_lengths(pts)
    rectangles = []

    def add(wall, offset, width, height, sill, label):
        if not isinstance(wall, int) or isinstance(wall, bool) or not 0 <= wall < len(lengths):
            raise ValueError(f"{label}: Ugyldig veggnummer.")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                   for v in (offset, width, height, sill)):
            raise ValueError(f"{label}: Ugyldige mål.")
        if offset < 0 or width <= 0 or offset+width > lengths[wall]+EPS:
            raise ValueError(f"{label} ligger utenfor veggen.")
        if sill < 0 or height <= 0 or sill+height > clear_height+EPS:
            raise ValueError(f"{label} må ligge mellom ferdig gulv og underkant tak.")
        for other_wall, x1, x2, z1, z2, other_label in rectangles:
            if (wall == other_wall and min(offset+width, x2)-max(offset, x1) > EPS
                    and min(sill+height, z2)-max(sill, z1) > EPS):
                raise ValueError(f"{label} overlapper {other_label.lower()} på vegg {wall+1}.")
        rectangles.append((wall, offset, offset+width, sill, sill+height, label))

    for i, door in enumerate(doors):
        if len(door) not in (2, 4, 5) or door[0] not in DOR_DB:
            raise ValueError("Ugyldig dør.")
        key, count = door[:2]
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 10:
            raise ValueError("Antall dører må være et heltall fra 0 til 10.")
        width, height = DOR_DB[key]["bw"]/1000, DOR_DB[key]["bh"]/1000
        if count and height > clear_height+EPS:
            raise ValueError("Døren er høyere enn fri høyde over ferdig gulv.")
        if len(door) > 2:
            for k in range(count):
                add(door[2], door[3]+k*(width+.2), width, height, 0, f"Dør {i+1}.{k+1}")
    for i, opening in enumerate(openings or []):
        if len(opening) != 6:
            raise ValueError("Ugyldig åpning.")
        add(*opening[:5], f"Åpning {i+1}")

def poly_area_raw(pts: Sequence[Point]) -> float:
    a = np.array(pts, dtype=float)
    x, y = a[:, 0], a[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

def poly_area(pts: Sequence[Point]) -> float:
    validate_polygon(pts)
    return poly_area_raw(pts)

def poly_perim(pts: Sequence[Point]) -> float:
    validate_polygon(pts)
    a = np.array(pts, dtype=float)
    return float(np.sum(np.linalg.norm(np.roll(a, -1, axis=0) - a, axis=1)))

def wall_lengths(pts: Sequence[Point]) -> list[float]:
    validate_polygon(pts)
    a = np.array(pts, dtype=float)
    return np.linalg.norm(np.roll(a, -1, axis=0) - a, axis=1).tolist()

def ensure_ccw(pts: Sequence[Point]) -> list[Point]:
    """Sørger for at polygon er moturs (CCW)."""
    validate_polygon(pts)
    a = np.array(pts, dtype=float)
    x, y = a[:, 0], a[:, 1]
    signed = np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))
    return list(pts) if signed > 0 else list(reversed(pts))

def classify_corners(pts: Sequence[Point]) -> tuple[int, int]:
    """Returnerer antall innvendige og utvendige/re-entrant hjørner."""
    pts_ccw = ensure_ccw(pts)
    a = np.array(pts_ccw, dtype=float)
    n_inn = 0
    n_ut = 0
    for i in range(len(a)):
        pm = a[(i - 1) % len(a)]
        pc = a[i]
        pn = a[(i + 1) % len(a)]
        v1 = pc - pm
        v2 = pn - pc
        cross = float(v1[0] * v2[1] - v1[1] * v2[0])
        if cross >= 0:
            n_inn += 1
        else:
            n_ut += 1
    return n_inn, n_ut

def beslag_beregning(pts: Sequence[Point], H: float, excluded_walls=(), thickness=0.0, inner_height=None, floor_angles=False) -> dict:
    """Beregner lm og antall 2,5 m-stenger for innvendig/utvendig L-beslag."""
    if H <= 0:
        raise ValueError("Romhøyde må være større enn 0.")
    STANG_M = 2.5
    excluded = set(excluded_walls)
    from finishing import trim_cuts
    corners = [i for i in range(len(pts)) if i not in excluded and (i-1)%len(pts) not in excluded]
    n_inn = n_ut = len(corners)
    runs = [(f"V{i+1} tak",length) for i,length in enumerate(wall_lengths(pts)) if i not in excluded]
    perim = sum(length for _,length in runs)
    from construction import floor_outline
    inner_height = H if inner_height is None else inner_height
    outer = floor_outline(pts,thickness) if thickness else pts
    outer_runs = [(f"V{i+1} tak",length) for i,length in enumerate(wall_lengths(outer)) if i not in excluded]
    floor_runs = [(label.replace("tak","gulv"),length) for label,length in runs] if floor_angles else []
    outer_floor_runs = [(label.replace("tak","gulv"),length) for label,length in outer_runs] if floor_angles else []
    cuts = trim_cuts([(f"H{i+1} vegg",inner_height) for i in corners]+runs+floor_runs)
    outer_cuts = trim_cuts([(f"H{i+1} vegg",H) for i in corners]+outer_runs+outer_floor_runs)
    lm_inn_hjorne, lm_ut_hjorne = len(corners)*inner_height, len(corners)*H
    lm_inn_tak, lm_ut_tak = perim, sum(length for _,length in outer_runs)
    lm_inn_tot, lm_ut_tot = lm_inn_hjorne+lm_inn_tak+sum(v for _,v in floor_runs), lm_ut_hjorne+lm_ut_tak+sum(v for _,v in outer_floor_runs)
    from finishing import trim_order
    stk_inn, stk_ut = trim_order(lm_inn_tot),trim_order(lm_ut_tot)
    return dict(
        kapp_inn=cuts, kapp_ut=outer_cuts, n_inn=n_inn, n_ut=n_ut, perim=round(perim, 2),
        lm_inn_hjorne=round(lm_inn_hjorne, 2), lm_inn_tak=round(lm_inn_tak, 2),
        lm_inn_tot=round(lm_inn_tot, 2), stk_inn=stk_inn,
        lm_ut_hjorne=round(lm_ut_hjorne, 2), lm_ut_tak=round(lm_ut_tak, 2),
        lm_ut_tot=round(lm_ut_tot, 2), stk_ut=stk_ut,
    )
