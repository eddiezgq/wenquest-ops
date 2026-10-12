"""An in-memory stand-in for ERPNext's REST API, following its rules for filters, ordering and paging.

Only what WenQuest Ops uses: GET /api/resource/<doctype> (filters with = > < >= <= in, fields, order_by,
limit_start, limit_page_length), GET/PUT /api/resource/<doctype>/<name>, POST /api/resource/<doctype>, ping.
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
            body = json.loads(request.content)
            name = body.get("name") or f"{doctype[:3].upper()}-{len(store) + 1:05d}"
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
