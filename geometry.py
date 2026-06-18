from __future__ import annotations
import math
from typing import Sequence, Tuple
import numpy as np

Point = Tuple[float, float]
EPS = 1e-6

def mm_to_m(value_mm: float) -> float:
    """Konverterer millimeter til meter."""
    return value_mm / 1000.0

def m_to_mm(value_m: float) -> int:
    """Konverterer meter til millimeter, avrundet til nærmeste heltall."""
    return int(round(value_m * 1000))

def validate_polygon(pts: Sequence[Point]) -> None:
    """Validerer at polygonet har nok punkter og ikke inneholder duplikater."""
    if len(pts) < 3:
        raise ValueError("Polygon må ha minst 3 punkter.")
    rounded = {(round(float(x), 6), round(float(y), 6)) for x, y in pts}
    if len(rounded) != len(pts):
        raise ValueError("Polygonet inneholder dupliserte hjørnepunkter.")
    if poly_area_raw(pts) <= EPS:
        raise ValueError("Polygonet har null eller negativt areal.")

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

def beslag_beregning(pts: Sequence[Point], H: float) -> dict:
    """Beregner lm og antall 2,5 m-stenger for innvendig/utvendig L-beslag."""
    if H <= 0:
        raise ValueError("Romhøyde må være større enn 0.")
    STANG_M = 2.5
    n_inn, n_ut = classify_corners(pts)
    perim = poly_perim(pts)
    lm_inn_hjorne = n_inn * H
    lm_inn_tak = perim
    lm_inn_tot = lm_inn_hjorne + lm_inn_tak
    stk_inn = math.ceil(lm_inn_tot / STANG_M)
    lm_ut_hjorne = n_ut * H
    lm_ut_tak = perim
    lm_ut_tot = lm_ut_hjorne + lm_ut_tak
    stk_ut = math.ceil(lm_ut_tot / STANG_M)
    return dict(
        n_inn=n_inn, n_ut=n_ut, perim=round(perim, 2),
        lm_inn_hjorne=round(lm_inn_hjorne, 2), lm_inn_tak=round(lm_inn_tak, 2),
        lm_inn_tot=round(lm_inn_tot, 2), stk_inn=stk_inn,
        lm_ut_hjorne=round(lm_ut_hjorne, 2), lm_ut_tak=round(lm_ut_tak, 2),
        lm_ut_tot=round(lm_ut_tot, 2), stk_ut=stk_ut,
    )
