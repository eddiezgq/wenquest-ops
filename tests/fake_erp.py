"""An in-memory stand-in for ERPNext's REST API, following its rules for filters, ordering and paging.

Only what WenQuest Ops uses: GET /api/resource/<doctype> (filters with = > < >= <= in, fields, order_by,
limit_start, limit_page_length), GET/PUT /api/resource/<doctype>/<name>, POST /api/resource/<doctype>, ping, the
signed-in user. Like ERPNext, a quality inspection needs an existing user as inspected_by: left out, ERPNext's
default is the literal "user", which is refused.
Documents are fictional test data.
"""

from __future__ import annotations

import json
import urllib.parse

import httpx

OPS = {"=": lambda a, b: a == b, ">": lambda a, b: a > b, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b,
       "<=": lambda a, b: a <= b, "in": lambda a, b: a in b}


class FakeErp:
    def __init__(self):
        self.docs: dict[str, dict[str, dict]] = {}
        self.requests: list[httpx.Request] = []
        self.fail_after: int | None = None  # simulate a dropped connection after this many requests
        self.clock = 0
        self.users = {"Administrator"}      # ERPNext users; the API key signs in as the first
        self.api_user = "Administrator"

    def tick(self) -> str:
        self.clock += 1
        return f"2026-10-12 09:{self.clock // 60:02d}:{self.clock % 60:02d}.000000"

    def put(self, doctype: str, name: str, modified: str | None = None, **fields) -> dict:
        doc = {"name": name, "doctype": doctype, "docstatus": 0, **self.docs.get(doctype, {}).get(name, {}), **fields}
        doc["modified"] = modified or self.tick()
        self.docs.setdefault(doctype, {})[name] = doc
        return doc

    def delete(self, doctype: str, name: str) -> None:
        self.docs[doctype].pop(name)
        at = self.tick()
        self.put("Deleted Document", f"DEL-{self.clock:04d}", modified=at, creation=at, deleted_doctype=doctype,
                 deleted_name=name)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_after is not None and len(self.requests) > self.fail_after:
            raise httpx.ConnectError("connection dropped", request=request)
        path = urllib.parse.unquote(request.url.path)
        if path == "/api/method/ping":
            return httpx.Response(200, json={"message": "pong"})
        if path == "/api/method/frappe.auth.get_logged_user":
            return httpx.Response(200, json={"message": self.api_user})
        if path == "/api/method/erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry":
            args = json.loads(request.content)
            inv = self.docs.get(args["dt"], {}).get(args["dn"])
            if inv is None:
                return httpx.Response(404, json={"exc_type": "DoesNotExistError"})
            party = "Customer" if args["dt"] == "Sales Invoice" else "Supplier"
            return httpx.Response(200, json={"message": {
                "doctype": "Payment Entry", "name": "new-payment-entry-1", "__islocal": 1, "docstatus": 0,
                "payment_type": "Receive" if party == "Customer" else "Pay", "party_type": party,
                "party": inv.get(party.lower()), "paid_amount": inv.get("grand_total"),
                "references": [{"name": "new-row-1", "reference_doctype": args["dt"], "reference_name": args["dn"],
                                "allocated_amount": inv.get("grand_total")}]}})
        if path.startswith("/api/resource/User/") and request.method == "GET":
            name = path.removeprefix("/api/resource/User/")
            if name not in self.users:
                return httpx.Response(404, json={"exc_type": "DoesNotExistError"})
            return httpx.Response(200, json={"data": {"name": name, "doctype": "User"}})
        parts = path.removeprefix("/api/resource/").split("/", 1)
        doctype = parts[0]
        store = self.docs.setdefault(doctype, {})
        if len(parts) == 2:
            doc = store.get(parts[1])
            if doc is None:
                return httpx.Response(404, json={"exc_type": "DoesNotExistError"})
            if request.method == "PUT":
                doc = self.put(doctype, parts[1], **json.loads(request.content))
            return httpx.Response(200, json={"data": doc})
        if request.method == "POST":
            body = {k: v for k, v in json.loads(request.content).items() if k not in ("doctype", "name", "modified")}
            named_by = {"Item": "item_code", "Customer": "customer_name", "Supplier": "supplier_name",
                        "Item Group": "item_group_name", "Quality Inspection Parameter": "parameter"}.get(doctype)
            if doctype == "Quality Inspection" and body.setdefault("inspected_by", "user") not in self.users:
                return httpx.Response(417, json={"exception": "frappe.exceptions.LinkValidationError: "
                                                              f"Could not find Inspected By: {body['inspected_by']}"})
            name = body.get(named_by) if named_by else None
            name = name or f"{doctype[:3].upper()}-{len(store) + 1:05d}"
            for i, row in enumerate(body.get("items") or [], start=1):   # child rows get names, as in ERPNext
                row.setdefault("name", f"{name}-{i}")
            return httpx.Response(200, json={"data": self.put(doctype, name, **body)})
        q = request.url.params
        rows = list(store.values())
        for f in json.loads(q.get("filters", "[]")):
            field, op, value = f[-3:]
            rows = [r for r in rows if field in r and OPS[op](r[field], value)]
        for key in reversed([k.strip() for k in q.get("order_by", "modified desc").split(",")]):
            field, _, direction = key.partition(" ")
            rows.sort(key=lambda r, f=field: r[f], reverse=direction.strip().lower() == "desc")
        start, length = int(q.get("limit_start", 0)), int(q.get("limit_page_length", 20))
        rows = rows[start:start + length] if length else rows[start:]
        fields = json.loads(q.get("fields", '["name"]'))
        if fields != ["*"]:
            rows = [{k: r.get(k) for k in fields} for r in rows]
        return httpx.Response(200, json={"data": rows})
