"""Exterior editor dimensions; the construction engine retains clear inside geometry."""
import numpy as np
from construction import floor_outline, wall_outer_face_span
from geometry import validate_polygon, polygon_winding


def inside_from_outside(points, thickness):
    inside = floor_outline(points, -thickness)
    validate_polygon(inside)
    if polygon_winding(inside) != polygon_winding(points):
        raise ValueError("Paneltykkelsen er for stor for rommets mål.")
    # Reject collapsed narrow arms, even if the offset still makes a simple polygon.
    for a, b, c, d in zip(points, np.roll(points, -1, axis=0), inside, np.roll(inside, -1, axis=0)):
        if np.dot(np.subtract(b, a), np.subtract(d, c)) <= 0:
            raise ValueError("Rommet er for smalt for valgt paneltykkelse.")
    return inside


def corner_shift(inside, thickness, wall):
    """Distance along a wall from its outside start corner to its inside start."""
    a = np.asarray(inside, float)
    outer = np.asarray(floor_outline(a, thickness))
    direction = a[(wall+1) % len(a)] - a[wall]
    direction /= np.linalg.norm(direction)
    return float((a[wall] - outer[wall]) @ direction)


def exterior_wall(inside, thickness, wall, excluded_walls=()):
    """Outside measurement endpoints, stopping at free ends beside omitted walls."""
    a = np.asarray(inside[wall], dtype=float)
    direction = np.asarray(inside[(wall+1) % len(inside)]) - a
    direction /= np.linalg.norm(direction)
    inward = polygon_winding(inside) * np.array([-direction[1], direction[0]])
    lo, hi = wall_outer_face_span(inside, wall, thickness, excluded_walls)
    origin = a - inward * thickness
    return origin + direction * lo, origin + direction * hi


def exterior_door(inside, thickness, wall, inside_offset, excluded_walls=()):
    start, end = exterior_wall(inside, thickness, wall, excluded_walls)
    length = float(np.linalg.norm(end-start))
    direction = (end-start) / length
    shift = float((np.asarray(inside[wall])-start) @ direction)
    return start, length, inside_offset + shift
