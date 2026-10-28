"""Quality tools, step 22a (ADR-0022): the arithmetic of a Pareto chart, a histogram and a scatter plot. Pure functions
on plain values; no AI and no network (tests/test_isolation.py). What a chart cannot say is unknown, never zero.

- Pareto: categories sorted by count, largest first (ties by name), with each share and the running share of the total
- Histogram: equal-width bins over the data, Sturges' rule for their number (k = ceil(log2 n) + 1, kept to 5-20),
  values outside the specification limits counted
- Scatter: Pearson's correlation coefficient and the least-squares line; it says how two values move together,
  not which one causes the other
"""

from __future__ import annotations

import math
import statistics as st

from wqops.i18n import say

NOT_RECORDED = "not recorded"


class ToolError(ValueError):
    pass


def pareto(counts: dict[str, float]) -> list[dict]:
    """``counts``: category -> count (or quantity). Zero categories are left out; a category with no value is the
    caller's ``NOT_RECORDED`` and is ranked like any other, so missing data stays visible."""
    items = sorted(((k, float(v)) for k, v in counts.items() if v), key=lambda kv: (-kv[1], kv[0]))
    total = sum(v for _, v in items)
    out, run = [], 0.0
    for k, v in items:
        run += v
        out.append({"key": k, "count": v, "share": v / total, "cumulative": run / total})
    if out:
        out[-1]["cumulative"] = 1.0              # no rounding drift at the end of the line
    return out


def vital_few(bars: list[dict], cut: float = 0.8) -> int:
    """How many of the largest categories it takes to reach ``cut`` of the total (the usual 80 %)."""
    for i, b in enumerate(bars, start=1):
        if b["cumulative"] >= cut - 1e-12:
            return i
    return len(bars)


def bins_for(n: int) -> int:
    return max(5, min(20, math.ceil(math.log2(n)) + 1)) if n > 0 else 0


def histogram(values: list[float], lsl: float | None = None, usl: float | None = None, bins: int | None = None) -> dict:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if len(vals) < 2:
        raise ToolError(say("at least 2 values are needed for a histogram"))
    lo, hi = min(vals), max(vals)
    k = bins or bins_for(len(vals))
    if hi == lo:                                 # no spread: one bin, centred on the value
        width = abs(lo) * 1e-3 or 1e-3
        edges = [lo - width / 2, lo + width / 2]
        counts = [len(vals)]
    else:
        width = (hi - lo) / k
        edges = [lo + i * width for i in range(k)] + [hi]
        counts = [0] * k
        for v in vals:
            counts[min(k - 1, int((v - lo) / width))] += 1
    below = sum(1 for v in vals if lsl is not None and v < lsl)
    above = sum(1 for v in vals if usl is not None and v > usl)
    return {"n": len(vals), "edges": edges, "counts": counts, "mean": st.fmean(vals), "s": st.stdev(vals),
            "min": lo, "max": hi, "LSL": lsl, "USL": usl, "below": below if lsl is not None else None,
            "above": above if usl is not None else None}


def correlation(pairs: list[tuple[float, float]]) -> dict:
    """Pearson's r, r squared and the least-squares line y = a + b x. Unknown (None) with fewer than 3 pairs or when
    either value does not vary."""
    pts = [(float(x), float(y)) for x, y in pairs if x is not None and y is not None]
    out = {"n": len(pts), "r": None, "r2": None, "slope": None, "intercept": None}
    if len(pts) < 3:
        out["note"] = say("unknown: at least 3 pairs are needed")
        return out
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mx, my = st.fmean(xs), st.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    if sxx == 0 or syy == 0:
        out["note"] = say("unknown: one of the two values does not vary")
        return out
    r = sxy / math.sqrt(sxx * syy)
    out.update(r=r, r2=r * r, slope=sxy / sxx, intercept=my - sxy / sxx * mx)
    a = abs(r)
    strength = "strong" if a >= 0.7 else "moderate" if a >= 0.4 else "weak"
    notes = {
        ("strong", True): say("strong positive correlation; it does not show which causes which"),
        ("strong", False): say("strong negative correlation; it does not show which causes which"),
        ("moderate", True): say("moderate positive correlation; it does not show which causes which"),
        ("moderate", False): say("moderate negative correlation; it does not show which causes which"),
        ("weak", True): say("weak positive correlation; it does not show which causes which"),
        ("weak", False): say("weak negative correlation; it does not show which causes which"),
    }
    out["note"] = notes[(strength, r > 0)]
    return out
