"""Executable regression for editable five-wall rooms, using millimetres."""
import math
from geometry import pentagon_sides, pentagon_parameters, update_pentagon_sides


def rejects(function, *args):
    try:
        function(*args)
    except ValueError:
        return
    raise AssertionError((function.__name__, args))


base = pentagon_sides(5850, 4450, 1100, 1100)
assert base[:2] == [5850, 3350] and base[3:] == [4750, 4450]
assert math.isclose(base[2], 1100*math.sqrt(2))
assert pentagon_parameters(base) == (5850, 4450, 1100, 1100)
for index, value in ((0, 6000), (1, 3000), (3, 4300), (4, 5000)):
    changed = update_pentagon_sides(base, index, value)
    assert changed[index] == value
    assert all(changed[i] == base[i] for i in range(5) if i not in (index, 2))
    length, width, cx, cy = pentagon_parameters(changed)
    assert math.isclose(changed[2], math.hypot(cx, cy))

for neighbour in (1, 3):
    changed = update_pentagon_sides(base, 2, 1800, neighbour)
    assert changed[2] == 1800 and changed[0] == base[0] and changed[4] == base[4]
    assert changed[4-neighbour] == base[4-neighbour]
    length, width, cx, cy = pentagon_parameters(changed)
    assert math.isclose(math.hypot(cx, cy), 1800, abs_tol=1e-9)
    assert changed[neighbour] != round(changed[neighbour]), "Do not round the derived wall."

asymmetric = pentagon_sides(5850.25, 4450.75, 1200.125, 700.625)
assert all(math.isclose(a, b, abs_tol=1e-9) for a, b in
           zip(pentagon_parameters(asymmetric), (5850.25, 4450.75, 1200.125, 700.625)))
assert math.degrees(math.atan2(700.625, 1200.125)) != 45
boundary = pentagon_sides(500, 500, 50, 50)
assert pentagon_parameters(boundary) == (500, 500, 50, 50)
for neighbour in (1, 3):
    minimum = update_pentagon_sides(base, 2, math.hypot(50, 1100), neighbour)
    _, _, cx, cy = pentagon_parameters(minimum)
    assert min(cx, cy) == 50.0, "Computed minimum cuts must remain valid when serialized."
# Existing files permit short positive straight walls; retain them unchanged.
short = pentagon_sides(5850, 4450, 5800, 4449)
assert short[1] == 1 and short[3] == 50
assert pentagon_parameters(short) == (5850, 4450, 5800, 4449)
assert update_pentagon_sides(base, 3, 50)[3] == 50
assert math.isclose(update_pentagon_sides(base, 2, math.hypot(5849, 1100))[3], 1, abs_tol=1e-9)

for args in ((499, 4450, 100, 100), (5850, 30001, 100, 100), (5850, 4450, 49, 100),
             (5850, 4450, 5850, 100), (5850, 4450, float('nan'), 100),
             (5850, 4450, -100, 100), (True, 4450, 100, 100)):
    rejects(pentagon_sides, *args)
for index, value, neighbour in ((0, 4700, 3), (1, 4440, 3), (3, 0, 3), (4, 3300, 3),
                               (2, 1000, 3), (2, 10000, 1), (2, 1e308, 3),
                               (2, float('nan'), 3), (2, -1, 3), (2, 1800, 4)):
    before = base.copy()
    rejects(update_pentagon_sides, base, index, value, neighbour)
    assert base == before
rejects(pentagon_parameters, [5850, 3350, 1556, 4750, 4450])
rejects(pentagon_parameters, [5850, 3350, float('inf'), 4750, 4450])
print('PASS: all five walls, both diagonal neighbours, fractional lengths and rejected impossible geometry')
