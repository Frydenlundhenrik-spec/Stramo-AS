from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Literal

import numpy as np

Point = tuple[float, float]

@dataclass(frozen=True)
class RoofFloorPanel:
    name: str
    kind: str
    width_mm: int
    span_mm: int
    area_m2: float
    polygon: list[Point]
    note: str


def _signed_area(pts: np.ndarray) -> float:
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _ensure_ccw_np(pts: Sequence[Point]) -> np.ndarray:
    a = np.array(pts, dtype=float)
    if len(a) < 3:
        raise ValueError("Polygon må ha minst 3 punkter")
    return a if _signed_area(a) > 0 else a[::-1].copy()


def polygon_area(pts: Sequence[Point]) -> float:
    a = np.array(pts, dtype=float)
    if len(a) < 3:
        return 0.0
    return abs(_signed_area(a))


def main_axis_from_longest_wall(pts: Sequence[Point]) -> tuple[np.ndarray, np.ndarray]:
    """Returnerer lokal X-retning langs lengste vegg og lokal Y-retning vinkelrett på denne."""
    a = _ensure_ccw_np(pts)
    best_len = -1.0
    best_dir = np.array([1.0, 0.0])
    for i in range(len(a)):
        p1 = a[i]
        p2 = a[(i + 1) % len(a)]
        v = p2 - p1
        L = float(np.linalg.norm(v))
        if L > best_len:
            best_len = L
            best_dir = v / L
    x_axis = best_dir
    y_axis = np.array([-x_axis[1], x_axis[0]])
    return x_axis, y_axis


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
    - Panelene legges langs rommets hovedretning, funnet fra lengste vegg.
    - Hvert panel klippes mot rompolygonet, slik at skrå hjørner får riktig kappform.
    - Kapp kan ligge først eller sist. Start/slutt trenger ikke være like store.
    """
    if panel_width_mm <= 0:
        raise ValueError('Elementbredde må være større enn 0')

    pts_np = _ensure_ccw_np(pts)
    x_axis, y_axis = main_axis_from_longest_wall(pts_np)
    origin = pts_np[0]
    local = world_to_local(pts_np, origin, x_axis, y_axis)

    x_min = float(local[:, 0].min())
    x_max = float(local[:, 0].max())
    total_mm = int(round((x_max - x_min) * 1000))
    panel_m = panel_width_mm / 1000.0
    total_m = total_mm / 1000.0
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
        x1 = min(cursor + width_mm / 1000.0, x_min + total_m)
        cursor = x1
        clipped_local = clip_polygon_between_x(local, x0, x1)
        if len(clipped_local) < 3:
            continue
        world = local_to_world(clipped_local, origin, x_axis, y_axis)
        span_mm = int(round((clipped_local[:, 1].max() - clipped_local[:, 1].min()) * 1000))
        area_m2 = round(polygon_area(clipped_local), 3)
        if width_mm == panel_width_mm:
            typ = f'{label} – hel'
            note_cut = ''
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
        ))
    return panels
