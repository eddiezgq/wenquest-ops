"""Company manifest and its Excel template (docs/plan.md, Phase 1 item 2)."""

from __future__ import annotations

import copy

import pytest
import yaml
from openpyxl import load_workbook

from wqops import company as C
from wqops import company_xlsx as X


@pytest.fixture
def demo():
    return yaml.safe_load(C.DEMO_FILE.read_text(encoding="utf-8"))


def test_demo_is_valid_and_marked_fictional(demo):
    assert C.validate(demo) == []
    assert demo["demo"] is True and "(Demo)" in demo["company"]["name"]
    assert "FICTIONAL" in C.DEMO_FILE.read_text(encoding="utf-8").splitlines()[0]
    assert all(p["email"].endswith("@demo.example") for p in demo["people"])
    m = C.load(C.DEMO_FILE)
    assert {r for p in m["people"] for r in p["roles"]} == set(C.ROLES)   # every role has someone in the demo


def test_defaults_are_filled(demo):
    del demo["company"]["units"], demo["company"]["fiscal_year_start"], demo["company"]["date_format"]
    m = C.normalize(demo)
    assert m["company"]["units"] == {"weight": "lb", "length": "in"}
    assert m["company"]["fiscal_year_start"] == "01-01" and m["company"]["date_format"] == "mm-dd-yyyy"


BREAKS = [
    (lambda m: m.update(version=2), "version"),
    (lambda m: m["company"].pop("currency"), "company.currency: required"),
    (lambda m: m["company"].update(abbr="TOOLONG1"), "company.abbr"),
    (lambda m: m["company"].update(currency="usd"), "company.currency: ISO"),
    (lambda m: m["company"].update(timezone="Mars/Base"), "company.timezone"),
    (lambda m: m["company"].update(fiscal_year_start="13-01"), "fiscal_year_start"),
    (lambda m: m["company"]["units"].update(weight="stone"), "units.weight"),
    (lambda m: m.update(sites=[]), "sites: at least one"),
    (lambda m: m["sites"][1].update(id="DC Tampa"), "sites[1].id"),
    (lambda m: m["sites"].append(dict(m["sites"][0])), "duplicate id"),
    (lambda m: m["sites"][0]["address"].pop("city"), "sites[0].address.city"),
    (lambda m: m["warehouses"][0].update(site="nowhere"), "warehouses[0].site"),
    (lambda m: m["warehouses"][0].update(kind="attic"), "warehouses[0].kind"),
    (lambda m: m["people"][1].update(email="not-an-email"), "people[1].email"),
    (lambda m: m["people"][2].update(email="DANA@demo.example"), "duplicate email"),
    (lambda m: m["people"][1].update(roles=["boss"]), "unknown role"),
    (lambda m: m["people"][0].update(roles=["sales"]), "owner role"),
    (lambda m: m["people"][1].update(department="nowhere"), "people[1].department"),
    (lambda m: m.update(modules=["ai"]), "'core' is always required"),
    (lambda m: m.update(modules=["core", "hub", "crm"]), "unknown module"),
    (lambda m: m.update(demo="yes"), "demo"),
]


@pytest.mark.parametrize(("breaker", "words"), BREAKS)
def test_each_error_is_reported(demo, breaker, words):
    m = copy.deepcopy(demo)
    breaker(m)
    errs = C.validate(m)
    assert any(words in e for e in errs), errs


def test_load_raises_with_all_errors(tmp_path, demo):
    demo["company"].pop("name")
    demo["warehouses"][0]["kind"] = "attic"
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(demo), encoding="utf-8")
    with pytest.raises(C.CompanyError) as exc:
        C.load(p)
    assert len(exc.value.errors) == 2
    p.write_text("company: [unclosed", encoding="utf-8")
    with pytest.raises(C.CompanyError, match="not valid YAML"):
        C.load(p)


def test_excel_round_trip(tmp_path):
    x = tmp_path / "company.xlsx"
    X.write_template(x, C.load(C.DEMO_FILE))
    wb = load_workbook(x)
    assert wb.sheetnames == ["Instructions", "Company", "Sites", "Warehouses", "Departments", "People", "Modules"]
    assert X.read(x) == C.load(C.DEMO_FILE)


def _edit(path, sheet, cell, value):
    wb = load_workbook(path)
    wb[sheet][cell] = value
    wb.save(path)


def test_excel_errors_point_at_sheet_row_column(tmp_path):
    x = tmp_path / "company.xlsx"
    X.write_template(x, C.load(C.DEMO_FILE))
    _edit(x, "People", "B4", "not-an-email")        # third person (rows 1-2 are header and help)
    _edit(x, "Warehouses", "C5", "nowhere")         # third warehouse
    _edit(x, "Company", "B6", "")                    # Currency row emptied
    _edit(x, "Modules", "B2", "maybe")
    with pytest.raises(C.CompanyError) as exc:
        X.read(x)
    text = "\n".join(exc.value.errors)
    assert "People row 4, Email: a valid email address" in text
    assert "Warehouses row 5, Site ID" in text
    assert "Company row 6, Currency: required" in text
    assert "Modules row 2, Turn on: yes or no" in text


def test_excel_blank_rows_ignored_and_roles_split(tmp_path):
    x = tmp_path / "company.xlsx"
    m = C.load(C.DEMO_FILE)
    X.write_template(x, m)
    wb = load_workbook(x)
    ws = wb["People"]
    ws.append([None, None, None, None])
    ws.append(["Casey Both", "casey@demo.example", "sales, quality", "sales"])
    wb.save(x)
    got = X.read(x)
    assert got["people"][-1] == {"name": "Casey Both", "email": "casey@demo.example", "roles": ["sales", "quality"],
                                 "department": "sales"}


def test_cli(tmp_path, capsys):
    out = tmp_path / "c.yaml"
    assert C.main(["export-demo", str(out)]) == 0
    assert C.main(["check", str(out)]) == 0
    assert "Harbor Lane Supply (Demo)" in capsys.readouterr().out
    x = tmp_path / "t.xlsx"
    assert C.main(["template", str(x)]) == 0
    assert C.main(["import", str(x), str(tmp_path / "back.yaml")]) == 0
    assert C.load(tmp_path / "back.yaml") == C.load(C.DEMO_FILE)
    out.write_text("version: 1\n", encoding="utf-8")
    assert C.main(["check", str(out)]) == 1
    assert "company: required" in capsys.readouterr().err
