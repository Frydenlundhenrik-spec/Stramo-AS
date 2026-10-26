"""Exterior editor dimensions; the construction engine retains clear inside geometry."""
import numpy as np
from construction import floor_outline
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


def exterior_door(inside, thickness, wall, inside_offset):
    outer = np.asarray(floor_outline(inside, thickness))
    length = float(np.linalg.norm(outer[(wall+1) % len(outer)]-outer[wall]))
    return outer[wall], length, inside_offset + corner_shift(inside, thickness, wall)
