"""Incoming inspection judgement, step 17b (ADR-0017; dee-qms PLAN-IQC, PLAN-SEVERITY): sampling table lookup,
readings, sample units and the lot, and switching suggestions, checked by hand. The table rows are made-up numbers
for the tests, not taken from any standard."""

import pytest

from wqops.hub.quality import sampling as S

ROWS = [
    {"id": 1, "aql": 1.0, "level": "normal", "lot_min": 2, "lot_max": 50, "n": 5, "ac": 0, "re": 1},
    {"id": 2, "aql": 1.0, "level": "normal", "lot_min": 51, "lot_max": 500, "n": 20, "ac": 1, "re": 2},
    {"id": 3, "aql": 1.0, "level": "tightened", "lot_min": 51, "lot_max": 500, "n": 32, "ac": 1, "re": 2},
    {"id": 4, "aql": 2.5, "level": "normal", "lot_min": 51, "lot_max": 500, "n": 20, "ac": 2, "re": 3,
     "active": False},
]
LEN = {"name": "Length", "kind": "measured", "lsl": 9.8, "usl": 10.2, "unit": "mm"}
TOP = {"name": "Head height", "kind": "measured", "lsl": None, "usl": 4.0, "unit": "mm"}
FIN = {"name": "Finish", "kind": "attribute", "lsl": None, "usl": None, "unit": ""}
RULES = [
    {"id": 1, "from_level": "normal", "to_level": "tightened", "condition": "window_rejected", "n": 5, "k": 2},
    {"id": 2, "from_level": "tightened", "to_level": "normal", "condition": "consecutive_accepted", "n": 5},
    {"id": 3, "from_level": "normal", "to_level": "reduced", "condition": "consecutive_accepted", "n": 10},
    {"id": 4, "from_level": "reduced", "to_level": "normal", "condition": "any_rejected"},
]


def test_lookup():
    assert S.lookup(ROWS, 1.0, "normal", 120)["id"] == 2
    assert S.lookup(ROWS, 1, "tightened", 500)["id"] == 3
    with pytest.raises(S.SamplingError, match="no row for AQL 1, reduced inspection, lot size 120"):
        S.lookup(ROWS, 1.0, "reduced", 120)
    with pytest.raises(S.SamplingError, match="no row"):
        S.lookup(ROWS, 2.5, "normal", 120)                       # archived rows are not used
    with pytest.raises(S.SamplingError, match="overlapping"):
        S.lookup([*ROWS, {**ROWS[1], "id": 9, "lot_min": 400}], 1.0, "normal", 450)
    # a lot smaller than the sample: every piece
    assert S.plan_for(ROWS[0], 3) == {"n": 3, "ac": 0, "re": 1, "all": True}
    assert S.plan_for(ROWS[1], 120) == {"n": 20, "ac": 1, "re": 2, "all": False}


def test_rows_and_characteristics_checked():
    assert S.check_row(ROWS[0]) == []
    assert S.check_row({**ROWS[0], "re": 2}) == ["n is at least 1, Ac at least 0 and Re is Ac + 1"]
    assert S.check_row({**ROWS[0], "lot_max": 1}) == ["the lot size range 2-1 is not a range"]
    assert S.check_row({**ROWS[0], "level": "strict", "aql": 0}) == [
        "the inspection level is normal, tightened or reduced", "the AQL is a number above 0"]
    assert S.check_characteristics([LEN, TOP, FIN]) == []
    assert S.check_characteristics([]) == ["a plan has at least one characteristic"]
    assert S.check_characteristics([LEN, {**LEN, "name": "length"}]) == ["characteristic 'length' twice"]
    assert S.check_characteristics([{**FIN, "usl": 1}]) == ["Finish: an attribute is pass or fail, with no limits "
                                                            "or unit"]
    assert S.check_characteristics([{**LEN, "lsl": None, "usl": None}]) == [
        "Length: a measured characteristic needs a lower or an upper limit"]
    assert S.check_characteristics([{**LEN, "lsl": 11}]) == ["Length: the lower limit is above the upper limit"]


def test_readings_units_and_the_lot():
    assert S.conforms(LEN, 9.8) and S.conforms(LEN, 10.2) and not S.conforms(LEN, 10.21)
    assert S.conforms(TOP, -50) and not S.conforms(TOP, 4.01)       # only the limit that is set
    assert S.conforms(FIN, passed=False) is False and S.conforms(FIN) is None and S.conforms(LEN) is None
    chars = [LEN, FIN]

    def rd(*units):
        out = []
        for i, (length, finish) in enumerate(units, start=1):
            out += [{"sample": i, "characteristic": "Length", "value": length},
                    {"sample": i, "characteristic": "Finish", "passed": finish}]
        return out
    ok = [(10.0, True)] * 5
    assert S.judge(chars, rd(*ok), 5, 0, 1) == {"defectives": 0, "failed_samples": [], "result": "accept"}
    # one unit failing two characteristics is one failing unit
    one = [(10.5, False)] + [(10.0, True)] * 4
    assert S.judge(chars, rd(*one), 5, 1, 2) == {"defectives": 1, "failed_samples": [1], "result": "accept"}
    two = [(10.5, True), (10.0, False)] + [(10.0, True)] * 3
    assert S.judge(chars, rd(*two), 5, 1, 2)["result"] == "reject"
    with pytest.raises(S.SamplingError, match="1 readings not entered yet, first: sample 5, Length"):
        S.judge(chars, rd(*ok[:4], (None, True)), 5, 0, 1)
    with pytest.raises(S.SamplingError, match="expected 10 readings"):
        S.judge(chars, rd(*ok[:4]), 5, 0, 1)


def test_switching_suggestions():
    A, R = "accept", "reject"
    assert S.suggest(RULES, "normal", [A, R, A, A]) is None
    s = S.suggest(RULES, "normal", [A, R, A, R])
    assert s["to"] == "tightened" and s["reason"] == ("Normal to tightened: at least 2 of the last 5 lots rejected; "
                                                      "actually 2 of the last 4 lots rejected")
    assert S.suggest(RULES, "normal", [A, A, R, A, A, R])["to"] == "tightened"        # 2 in the last 5
    assert S.suggest(RULES, "normal", [R, R, A, A, A, A]) is None                       # only 1 in the last 5
    assert S.suggest(RULES, "tightened", [R, A, A, A, A, A])["to"] == "normal"
    assert S.suggest(RULES, "tightened", [A, A, A, A]) is None
    assert S.suggest(RULES, "normal", [A] * 10)["to"] == "reduced"
    assert S.suggest(RULES, "reduced", [A, A, R])["to"] == "normal"
    assert S.suggest([{**r, "active": False} for r in RULES], "reduced", [R]) is None
    assert S.check_rule(RULES[0]) == [] and S.check_rule(RULES[3]) == []
    assert S.check_rule({"from_level": "reduced", "to_level": "tightened", "condition": "any_rejected"}) == [
        "reduced cannot go straight to tightened; it goes back to normal first"]
    assert S.check_rule({**RULES[0], "k": 6}) == ["K is a whole number from 1 to N"]
