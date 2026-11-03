from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Literal

import numpy as np

Point = tuple[float, float]

ROOF_REMAINDER_LIMIT_MM = 30

@dataclass(frozen=True)
class RoofFloorPanel:
    name: str
    kind: str
    width_mm: int
    span_mm: int
    area_m2: float
    polygon: list[Point]
    note: str
    blank: tuple[Point, ...] = ()  # rectangular envelope before the roof profile cut
    cut_polygon: list[Point] | None = None  # nominal cut shape when the roof layout distributes a remainder


def _signed_area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _ordered_points_np(pts: Sequence[Point]) -> np.ndarray:
    a = np.array(pts, dtype=float)
    if len(a) < 3:
        raise ValueError("Polygon må ha minst 3 punkter")
    # Mirroring changes winding, not wall identity. Reversing the vertices would
    # move the end offcut to the other side and change the ordering quantities.
    return a


def polygon_area(pts: Sequence[Point]) -> float:
    a = np.array(pts, dtype=float)
    if len(a) < 3:
        return 0.0
    return abs(_signed_area(a))


def main_axis_from_longest_wall(pts: Sequence[Point]) -> tuple[np.ndarray, np.ndarray]:
    """Returnerer lokal X-retning langs lengste vegg og lokal Y-retning vinkelrett på denne."""
    a = _ordered_points_np(pts)
    best_len = -1.0
    best_dir = np.array([1.0, 0.0])
    for i in range(len(a)):
        p1 = a[i]
        p2 = a[(i + 1) % len(a)]
        v = p2 - p1
        L = float(np.linalg.norm(v))
        if L > best_len + 1e-9:
            best_len = L
            best_dir = v / L
    x_axis = best_dir
    y_axis = np.array([-x_axis[1], x_axis[0]])
    return x_axis, y_axis


def _panel_axes(pts: np.ndarray, prefix: str) -> tuple[np.ndarray, np.ndarray]:
    if prefix == "T":
        edges = np.roll(pts, -1, axis=0) - pts
        lengths = np.linalg.norm(edges, axis=1)
        if np.all(lengths > 1e-9):
            unit = edges / lengths[:, None]
            prev = np.roll(unit, 1, axis=0)
            dot = np.abs((prev * unit).sum(axis=1))
            winding = np.sign(_signed_area(pts))
            right = (dot < 1e-8) & (winding*(prev[:, 0]*unit[:, 1] - prev[:, 1]*unit[:, 0]) > 0)
            if right.any() and np.any((dot > 1e-8) & (dot < 1-1e-8)):
                # On a clipped rectangle the two uninterrupted back walls have
                # square corners at both ends. On a right triangle each has one.
                both = right & np.roll(right, -1)
                candidates = np.flatnonzero(both if both.sum() >= 2 else right | np.roll(right, -1))
                shortest = min(candidates, key=lambda i: round(float(lengths[i]), 9))
                span = unit[shortest]
                # Point into the room so T1 starts at the back wall, even after mirroring.
                across = winding * np.array([-span[1], span[0]])
                return across, span
    return main_axis_from_longest_wall(pts)


def world_to_local(pts: Sequence[Point], origin: np.ndarray, x_axis: np.ndarray, y_axis: np.ndarray) -> np.ndarray:
    a = np.array(pts, dtype=float) - origin
    return np.column_stack((a @ x_axis, a @ y_axis))


def local_to_world(pts_local: Sequence[Point], origin: np.ndarray, x_axis: np.ndarray, y_axis: np.ndarray) -> list[Point]:
    a = np.array(pts_local, dtype=float)
    out = origin + np.outer(a[:, 0], x_axis) + np.outer(a[:, 1], y_axis)
    return [(float(x), float(y)) for x, y in out]


def _clip_poly_x(poly: np.ndarray, x_limit: float, keep: Literal['ge', 'le'], eps: float = 1e-9) -> np.ndarray:
    if len(poly) == 0:
        return poly

    def inside(p: np.ndarray) -> bool:
        return p[0] >= x_limit - eps if keep == 'ge' else p[0] <= x_limit + eps

    def intersect(p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
        dx = p2[0] - p1[0]
        if abs(dx) < eps:
            return p1.copy()
        t = (x_limit - p1[0]) / dx
        return p1 + t * (p2 - p1)

    out: list[np.ndarray] = []
    prev = poly[-1]
    prev_inside = inside(prev)
    for cur in poly:
        cur_inside = inside(cur)
        if cur_inside:
            if not prev_inside:
                out.append(intersect(prev, cur))
            out.append(cur)
        elif prev_inside:
            out.append(intersect(prev, cur))
        prev, prev_inside = cur, cur_inside

    if not out:
        return np.empty((0, 2), dtype=float)

    cleaned: list[np.ndarray] = []
    for p in out:
        if not cleaned or np.linalg.norm(p - cleaned[-1]) > 1e-7:
            cleaned.append(p)
    if len(cleaned) > 1 and np.linalg.norm(cleaned[0] - cleaned[-1]) < 1e-7:
        cleaned.pop()
    return np.array(cleaned, dtype=float)


def clip_polygon_between_x(poly_local: np.ndarray, x0: float, x1: float) -> np.ndarray:
    clipped = _clip_poly_x(poly_local, x0, 'ge')
    clipped = _clip_poly_x(clipped, x1, 'le')
    if len(clipped) < 3 or polygon_area(clipped) < 1e-8:
        return np.empty((0, 2), dtype=float)
    return clipped


def generate_roof_floor_panels(
    pts: Sequence[Point],
    panel_width_mm: int,
    prefix: str = 'T',
    label: str = 'Tak',
    cut_position: Literal['start', 'end'] = 'end',
) -> list[RoofFloorPanel]:
    """
    Lager polygonbaserte tak-/gulvpaneler.

    Prinsipp:
    - Panelbredden er samme som veggelementene.
    - Ved skråtak er spennet parallelt med korteste rettvinklede bakvegg.
    - Hvert panel klippes mot rompolygonet, slik at skrå hjørner får riktig kappform.
    - På skråtak legges full elementbredde fra bakveggen og restbredden ved spissen.
    - Restbredder under 30 mm fordeles over taket og gir ingen egen bestillingspost.
    """
    if panel_width_mm <= 0:
        raise ValueError('Elementbredde må være større enn 0')

    pts_np = _ordered_points_np(pts)
    x_axis, y_axis = _panel_axes(pts_np, prefix)
    if prefix == 'T':
        cut_position = 'end'  # Start with a full roof strip; only the last may be narrower.
    origin = pts_np[0]
    local = world_to_local(pts_np, origin, x_axis, y_axis)

    x_min = float(local[:, 0].min())
    x_max = float(local[:, 0].max())
    extent_mm = (x_max - x_min) * 1000
    total_mm = int(round(extent_mm))
    full_count = total_mm // panel_width_mm
    # Compare before rounding to whole mm. Discard float noise from rotation.
    remainder = round(extent_mm - full_count * panel_width_mm, 6)
    distribute = prefix == 'T' and full_count > 0 and 0 < remainder < ROOF_REMAINDER_LIMIT_MM
    layout_x_axis = x_axis
    if distribute:
        # Clip in nominal material coordinates. Map the resulting strips back
        # over the full footprint for plan/3D/IFC, anchored at the first wall.
        total_mm = full_count * panel_width_mm
        layout_scale = extent_mm / total_mm
        origin = origin + x_min * x_axis
        local[:, 0] = (local[:, 0] - x_min) / layout_scale
        x_min, x_max = 0.0, total_mm / 1000.0
        layout_x_axis = layout_scale * x_axis
    n = int(math.ceil(total_mm / panel_width_mm))
    rest_mm = total_mm % panel_width_mm

    if cut_position == 'start' and rest_mm > 0:
        widths_mm = [rest_mm] + [panel_width_mm] * (n - 1)
    else:
        widths_mm = [panel_width_mm] * (n - 1) + [rest_mm if rest_mm > 0 else panel_width_mm]

    panels: list[RoofFloorPanel] = []
    cursor = x_min
    for idx, width_mm in enumerate(widths_mm, start=1):
        if width_mm <= 0:
            continue
        x0 = cursor
        x1 = x_max if idx == n else min(cursor + width_mm / 1000.0, x_max)
        cursor = x1
        clipped_local = clip_polygon_between_x(local, x0, x1)
        if len(clipped_local) < 3:
            continue
        world = local_to_world(clipped_local, origin, layout_x_axis, y_axis)
        ymin, ymax = clipped_local[:, 1].min(), clipped_local[:, 1].max()
        blank = ()
        if prefix == "T" and (x1 - x0) * (ymax - ymin) - polygon_area(clipped_local) > 1e-8:
            blank = tuple(local_to_world([(x0, ymin), (x1, ymin), (x1, ymax), (x0, ymax)],
                                         origin, layout_x_axis, y_axis))
        span_mm = int(round((clipped_local[:, 1].max() - clipped_local[:, 1].min()) * 1000))
        area_m2 = round(polygon_area(clipped_local), 3)
        if width_mm == panel_width_mm and abs(area_m2-width_mm*span_mm/1e6)<.002:
            typ = f'{label} – hel'
            note_cut = ''
        elif width_mm == panel_width_mm:
            typ = f'{label} – formkapp'
            note_cut = 'formkapp'
        elif idx == 1 and cut_position == 'start':
            typ = f'{label} – startkapp'
            note_cut = f'startkapp {width_mm} mm'
        else:
            typ = f'{label} – sluttkapp'
            note_cut = f'sluttkapp {width_mm} mm'
        note = f'{label}element {idx}/{len(widths_mm)} · går fra vegg til vegg · maks spenn {span_mm} mm'
        if note_cut:
            note += f' · {note_cut}'
        if len(clipped_local) > 4:
            note += ' · polygonkapp mot skrå/avskåret vegg'
        panels.append(RoofFloorPanel(
            name=f'{prefix}{idx}',
            kind=typ,
            width_mm=int(width_mm),
            span_mm=span_mm,
            area_m2=area_m2,
            polygon=world,
            note=note,
            blank=blank,
            cut_polygon=local_to_world(clipped_local, origin, x_axis, y_axis) if distribute else None,
        ))
    return panels
