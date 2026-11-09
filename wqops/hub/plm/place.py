"""Where a part sits in its assembly (PLM step 27a, round 124): a placement is a move p = [x, y, z] in millimetres and
a turn q = [x, y, z, w] (a unit quaternion), the part's own frame in the assembly's frame. One per use: a line with
quantity 3 has three. Pure arithmetic, no CAD library."""

from __future__ import annotations

import math

from wqops.i18n import say

LIMIT = 1e6           # mm: anything further away is a mistake in the file


class PlaceError(ValueError):
    pass


def clean(x) -> dict:
    """A placement from a file or a request, checked: finite numbers, a turn of length about 1 (made exactly 1)."""
    if not isinstance(x, dict):
        raise PlaceError(say("a placement is a move p and a turn q"))
    p, q = x.get("p"), x.get("q", [0, 0, 0, 1])
    if not (isinstance(p, list) and len(p) == 3 and isinstance(q, list) and len(q) == 4):
        raise PlaceError(say("a placement is a move p and a turn q"))
    try:
        p, q = [float(v) for v in p], [float(v) for v in q]
    except (TypeError, ValueError) as exc:
        raise PlaceError(say("a placement holds numbers")) from exc
    if not all(math.isfinite(v) and abs(v) <= LIMIT for v in p + q):
        raise PlaceError(say("a placement holds numbers"))
    n = math.sqrt(sum(v * v for v in q))
    if abs(n - 1) > 1e-3:
        raise PlaceError(say("the turn of a placement is not a unit quaternion"))
    return {"p": [round(v, 6) for v in p], "q": [round(v / n, 9) for v in q]}


def clean_list(xs, count: int | None) -> list[dict]:
    """Placements of one line: as many as the quantity when it is a whole number (else none are kept)."""
    if not isinstance(xs, list) or len(xs) > 10000:
        raise PlaceError(say("placements are a list"))
    out = [clean(x) for x in xs]
    if count is not None and out and len(out) != count:
        raise PlaceError(say("{n} placements for a quantity of {qty}", n=len(out), qty=count))
    return out


# ---- 4x4 matrices as 16 numbers, row by row

def matrix(pl: dict) -> list[float]:
    x, y, z, w = pl["q"]
    px, py, pz = pl["p"]
    return [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), px,
            2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), py,
            2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), pz,
            0.0, 0.0, 0.0, 1.0]


IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def mul(a: list[float], b: list[float]) -> list[float]:
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


def from_axes(origin, axis, ref) -> list[float]:
    """STEP's AXIS2_PLACEMENT_3D: origin, z axis, x direction (made square to z)."""
    z = _unit(axis or [0, 0, 1])
    xr = ref or ([1, 0, 0] if abs(z[0]) < 0.9 else [0, 1, 0])
    d = sum(a * b for a, b in zip(xr, z, strict=True))
    x = _unit([a - d * b for a, b in zip(xr, z, strict=True)])
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    o = origin or [0, 0, 0]
    return [x[0], y[0], z[0], o[0], x[1], y[1], z[1], o[1], x[2], y[2], z[2], o[2], 0.0, 0.0, 0.0, 1.0]


def inverse(m: list[float]) -> list[float]:
    """Of a rigid move (turn and shift)."""
    r = [[m[0], m[4], m[8]], [m[1], m[5], m[9]], [m[2], m[6], m[10]]]      # transposed turn
    t = [m[3], m[7], m[11]]
    s = [-sum(r[i][k] * t[k] for k in range(3)) for i in range(3)]
    return [r[0][0], r[0][1], r[0][2], s[0], r[1][0], r[1][1], r[1][2], s[1], r[2][0], r[2][1], r[2][2], s[2],
            0.0, 0.0, 0.0, 1.0]


def placement(m: list[float]) -> dict:
    """A rigid 4x4 back to {p, q}."""
    tr = m[0] + m[5] + m[10]
    if tr > 0:
        s = math.sqrt(tr + 1) * 2
        q = [(m[9] - m[6]) / s, (m[2] - m[8]) / s, (m[4] - m[1]) / s, s / 4]
    elif m[0] > m[5] and m[0] > m[10]:
        s = math.sqrt(1 + m[0] - m[5] - m[10]) * 2
        q = [s / 4, (m[1] + m[4]) / s, (m[2] + m[8]) / s, (m[9] - m[6]) / s]
    elif m[5] > m[10]:
        s = math.sqrt(1 + m[5] - m[0] - m[10]) * 2
        q = [(m[1] + m[4]) / s, s / 4, (m[6] + m[9]) / s, (m[2] - m[8]) / s]
    else:
        s = math.sqrt(1 + m[10] - m[0] - m[5]) * 2
        q = [(m[2] + m[8]) / s, (m[6] + m[9]) / s, s / 4, (m[4] - m[1]) / s]
    return clean({"p": [m[3], m[7], m[11]], "q": q})


def _unit(v) -> list[float]:
    n = math.sqrt(sum(a * a for a in v)) or 1.0
    return [a / n for a in v]
