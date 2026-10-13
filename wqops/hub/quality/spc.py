"""SPC (ADR-0009 item 6): control charts, special-cause rules and process capability from inspection readings.

Pure functions on lists of values, following Montgomery, Introduction to Statistical Quality Control, and the AIAG
SPC manual (constants for subgroups of 2-10). Adapted from freecad-ai-parts factory/digital/hub/spc.py.

- X-bar and R chart: limits x-double-bar +/- A2 * R-bar; R chart D3 * R-bar .. D4 * R-bar; sigma within = R-bar / d2
- Individuals and moving range: x-bar +/- 3 * MR-bar / 1.128
- Western Electric rules 1-4
- Cp, Cpk from the within-subgroup sigma; Pp, Ppk from the overall standard deviation
"""

from __future__ import annotations

import itertools
import statistics as st

D2 = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078}
A2 = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483, 7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}
D3 = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0.076, 8: 0.136, 9: 0.184, 10: 0.223}
D4 = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004, 7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777}


class SpcError(ValueError):
    pass


def xbar_r(groups: list[list[float]]) -> dict:
    n = len(groups[0]) if groups else 0
    if n not in D2 or any(len(g) != n for g in groups):
        raise SpcError("X-bar and R needs subgroups of the same size, 2 to 10")
    if len(groups) < 2:
        raise SpcError("at least 2 subgroups are needed")
    xb = [st.fmean(g) for g in groups]
    rr = [max(g) - min(g) for g in groups]
    xbb, rb = st.fmean(xb), st.fmean(rr)
    return {"kind": "xbar_r", "n": n, "k": len(groups), "points": xb, "R": rr, "center": xbb, "Rbar": rb,
            "UCL": xbb + A2[n] * rb, "LCL": xbb - A2[n] * rb, "UCL_R": D4[n] * rb, "LCL_R": D3[n] * rb,
            "sigma_within": rb / D2[n]}


def i_mr(values: list[float]) -> dict:
    if len(values) < 3:
        raise SpcError("at least 3 values are needed")
    mr = [abs(b - a) for a, b in itertools.pairwise(values)]
    xb, mrb = st.fmean(values), st.fmean(mr)
    s = mrb / D2[2]
    return {"kind": "i_mr", "points": list(values), "MR": mr, "center": xb, "MRbar": mrb, "UCL": xb + 3 * s,
            "LCL": xb - 3 * s, "UCL_MR": D4[2] * mrb, "sigma_within": s}


def special_causes(points: list[float], center: float, sigma: float) -> list[dict]:
    """Western Electric rules: 1 point beyond 3 sigma; 2 of 3 beyond 2 sigma on one side; 4 of 5 beyond 1 sigma on one
    side; 8 in a row on one side. Reports the first point of each run (index from 0)."""
    z = [(p - center) / sigma if sigma > 0 else 0.0 for p in points]

    def hit(rule: int, i: int) -> bool:
        if rule == 1:
            return abs(z[i]) > 3
        if rule == 4:
            return i >= 7 and (all(x > 0 for x in z[i - 7:i + 1]) or all(x < 0 for x in z[i - 7:i + 1]))
        m, k, lim = (3, 2, 2) if rule == 2 else (5, 4, 1)
        if i < m - 1:
            return False
        w = z[i - m + 1:i + 1]
        return any(sum(1 for x in w if sg * x > lim) >= k and sg * z[i] > lim for sg in (1, -1))

    text = {1: "point {} is beyond the 3-sigma limits", 2: "2 of 3 points beyond 2 sigma on one side (to point {})",
            3: "4 of 5 points beyond 1 sigma on one side (to point {})",
            4: "8 points in a row on one side of the center line (to point {}): the process mean may have shifted"}
    out = []
    for rule in (1, 2, 3, 4):
        prev = False
        for i in range(len(z)):
            h = hit(rule, i)
            if h and not prev:
                out.append({"rule": rule, "index": i, "text": text[rule].format(i + 1)})
            prev = h
    return sorted(out, key=lambda o: (o["index"], o["rule"]))


def capability(values: list[float], lsl: float, usl: float, sigma_within: float) -> dict:
    mu, s = st.fmean(values), st.stdev(values)
    tol = usl - lsl
    return {"mean": mu, "s": s, "sigma_within": sigma_within, "Cp": tol / (6 * sigma_within),
            "Cpk": min(usl - mu, mu - lsl) / (3 * sigma_within), "Pp": tol / (6 * s),
            "Ppk": min(usl - mu, mu - lsl) / (3 * s), "n": len(values), "LSL": lsl, "USL": usl}


def chart(subgroups: list[dict]) -> dict:
    """``subgroups``: [{inspection, date, values, min, max}] in time order. X-bar and R when every subgroup has the
    same size of 2-10 and there are at least 2; otherwise individuals of the subgroup means (at least 3)."""
    groups = [s["values"] for s in subgroups]
    sizes = {len(g) for g in groups}
    try:
        if len(sizes) == 1 and min(sizes) in D2 and len(groups) >= 2:
            ch = xbar_r(groups)
            sig = ch["sigma_within"] / ch["n"] ** 0.5
        else:
            ch = i_mr([st.fmean(g) for g in groups])
            sig = ch["sigma_within"]
    except SpcError as exc:
        return {"enough_data": False, "note": f"Not enough data for a control chart: {exc}.",
                "subgroups": len(groups)}
    values = [v for g in groups for v in g]
    lo, hi = subgroups[-1].get("min"), subgroups[-1].get("max")
    cap = capability(values, lo, hi, ch["sigma_within"]) if lo is not None and hi is not None and hi > lo and \
        len(values) >= 2 and st.stdev(values) > 0 and ch["sigma_within"] > 0 else None
    return {"enough_data": True, "chart": ch, "signals": special_causes(ch["points"], ch["center"], sig),
            "capability": cap, "labels": [f"{s['inspection']} {s['date']}" for s in subgroups],
            "out_of_spec": sum(1 for v in values if (lo is not None and v < lo) or (hi is not None and v > hi))}
