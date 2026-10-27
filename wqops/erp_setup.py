"""Create the business in ERPNext from the company manifest (docs/plan.md, Phase 1 item 3).

Run inside the hub container by install.sh / upgrade.sh. Idempotent: what already exists is left as it is.

    python -m wqops.erp_setup wizard-args /company/company.yaml   # two lines for bench execute (setup wizard)
    python -m wqops.erp_setup apply /company/company.yaml          # warehouses, departments, addresses
"""

from __future__ import annotations

import datetime as dt
import os
import sys

from wqops import company as C
from wqops.erp import ErpClient, ErpError
from wqops.i18n import say

ADDRESS_TYPES = {"office": "Office", "warehouse": "Warehouse", "plant": "Plant", "store": "Shop"}


def fiscal_year(fy_start: str, today: dt.date) -> tuple[dt.date, dt.date]:
    """The fiscal year that contains ``today``, given its start as MM-DD."""
    month, day = (int(x) for x in fy_start.split("-"))
    start = dt.date(today.year, month, day)
    if start > today:
        start = dt.date(today.year - 1, month, day)
    end = dt.date(start.year + 1, month, day) - dt.timedelta(days=1)
    return start, end


def wizard_args(m: dict, today: dt.date) -> tuple[dict, dict]:
    """Arguments for ERPNext's setup wizard: system settings, then company and fiscal year."""
    c = m["company"]
    start, end = fiscal_year(c["fiscal_year_start"], today)
    date_format = c["date_format"]
    system = {"system_settings_data": {"language": "en", "country": c["country"], "currency": c["currency"],
                                       "time_zone": c["timezone"], "date_format": date_format},
              "user_data": {}}
    setup = {"args": {"language": "English", "country": c["country"], "timezone": c["timezone"],
                      "currency": c["currency"], "company_name": c["name"],
                      "company_abbr": c["abbr"], "chart_of_accounts": "Standard",
                      "fy_start_date": start.isoformat(), "fy_end_date": end.isoformat(),
                      "setup_demo": 0, "enable_telemetry": 0}}
    return system, setup


def warehouse_name(m: dict, w: dict) -> str:
    return f"{w['name']} - {m['company']['abbr']}"


def apply(m: dict, erp: ErpClient) -> list[str]:
    """Create what the manifest describes; return a line per action."""
    company = m["company"]["name"]
    abbr = m["company"]["abbr"]
    if erp.get("Company", company) is None:
        raise ErpError(say("company {company} does not exist in ERPNext; run the setup wizard first",
                           company=repr(company)))
    done = []
    for w in m["warehouses"]:
        name = warehouse_name(m, w)
        if erp.get("Warehouse", name) is not None:
            done.append(f"warehouse {name}: exists")
            continue
        doc = {"doctype": "Warehouse", "warehouse_name": w["name"], "company": company,
               "parent_warehouse": f"All Warehouses - {abbr}"}
        if w["kind"] == "transit":
            doc["warehouse_type"] = "Transit"
        erp.insert(doc)
        done.append(f"warehouse {name}: created")
    for d in m["departments"]:
        if erp.find("Department", {"department_name": d["name"], "company": company}):
            done.append(f"department {d['name']}: exists")
            continue
        erp.insert({"doctype": "Department", "department_name": d["name"], "company": company})
        done.append(f"department {d['name']}: created")
    public, secret = os.environ.get("WQO_PUBLIC_URL"), os.environ.get("WQO_ERP_SSO_SECRET")
    if public and secret:
        from wqops.hub import erp_sso as S  # noqa: PLC0415

        key = S.social_login_key(public, secret)
        if erp.get("Social Login Key", S.PROVIDER) is None:
            erp.insert(key)
            done.append("ERPNext sign-in through WenQuest Ops: created")
        else:
            erp.update("Social Login Key", S.PROVIDER, {k: v for k, v in key.items() if k != "doctype"})
            done.append("ERPNext sign-in through WenQuest Ops: updated")
    for s in m["sites"]:
        a = s.get("address")
        if not a:
            done.append(f"address {s['name']}: none given")
            continue
        atype = ADDRESS_TYPES[s["kind"]]
        if erp.find("Address", {"address_title": s["name"], "address_type": atype}):
            done.append(f"address {s['name']}: exists")
            continue
        erp.insert({"doctype": "Address", "address_title": s["name"], "address_type": atype,
                    "address_line1": a["line1"], "city": a["city"], "state": a.get("state", ""),
                    "pincode": a["postal_code"], "country": a["country"], "is_your_company_address": 1,
                    "links": [{"link_doctype": "Company", "link_name": company}]})
        done.append(f"address {s['name']}: created")
    return done


def client_from_env(transport=None) -> ErpClient:
    return ErpClient(os.environ.get("WQO_ERP_URL", "http://erp-frontend:8080"), os.environ.get("WQO_ERP_API_KEY", ""),
                     os.environ.get("WQO_ERP_API_SECRET", ""), site=os.environ.get("WQO_ERP_SITE", "frontend"),
                     transport=transport)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("wizard-args", "apply"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        m = C.load(argv[1])
    except C.CompanyError as exc:
        print(exc, file=sys.stderr)
        return 1
    if argv[0] == "wizard-args":
        today = dt.datetime.now(dt.UTC).date()
        system, setup = wizard_args(m, today)
        print(repr(system))
        print(repr(setup))
        return 0
    try:
        for line in apply(m, client_from_env()):
            print(line)
    except ErpError as exc:
        print(f"ERPNext setup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
