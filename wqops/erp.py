"""Minimal ERPNext REST client (ADR-0002): the only way WenQuest Ops talks to ERPNext.

Uses token auth (``Authorization: token key:secret``). ``site`` sets the Host header when ERPNext is reached on an
internal address (inside Docker the site is called ``frontend``).
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx


class ErpError(RuntimeError):
    pass


class ErpClient:
    def __init__(self, url: str, api_key: str = "", api_secret: str = "", *, site: str | None = None,
                 timeout: float = 30, transport: httpx.BaseTransport | None = None):
        headers = {"Accept": "application/json"}
        if api_key and api_secret:
            headers["Authorization"] = f"token {api_key}:{api_secret}"
        if site:
            headers["Host"] = site
        self.http = httpx.Client(base_url=url.rstrip("/"), headers=headers, timeout=timeout, transport=transport)

    def _check(self, r: httpx.Response) -> Any:
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = body.get("exception") or body.get("message") or body.get("_server_messages") or r.text
            except ValueError:
                msg = r.text
            raise ErpError(f"ERPNext {r.request.method} {r.request.url.path} -> {r.status_code}: {str(msg)[:300]}")
        return r.json()

    def logged_user(self) -> str:
        """The ERPNext user the API key signs in as."""
        return self._check(self.http.get("/api/method/frappe.auth.get_logged_user"))["message"]

    def ping(self) -> bool:
        try:
            return self._check(self.http.get("/api/method/ping")).get("message") == "pong"
        except (httpx.HTTPError, ErpError, ValueError):
            return False

    def get(self, doctype: str, name: str) -> dict | None:
        r = self.http.get(f"/api/resource/{doctype}/{quote(name, safe='')}")
        if r.status_code == 404:
            return None
        return self._check(r)["data"]

    def find(self, doctype: str, filters: dict, fields: list[str] | None = None) -> list[dict]:
        params = {"filters": json.dumps([[doctype, k, "=", v] for k, v in filters.items()]),
                  "fields": json.dumps(fields or ["name"]), "limit_page_length": 0}
        return self._check(self.http.get(f"/api/resource/{doctype}", params=params))["data"]

    def list(self, doctype: str, *, filters: list | None = None, fields: list[str] | None = None,
             order_by: str = "modified asc, name asc", limit: int = 100, start: int = 0) -> list[dict]:
        """One page of ``doctype`` (all document states: draft, submitted, cancelled)."""
        params = {"filters": json.dumps(filters or []), "fields": json.dumps(fields or ["name"]),
                  "order_by": order_by, "limit_start": start, "limit_page_length": limit}
        return self._check(self.http.get(f"/api/resource/{doctype}", params=params))["data"]

    def update(self, doctype: str, name: str, values: dict) -> dict:
        return self._check(self.http.put(f"/api/resource/{doctype}/{quote(name, safe='')}", json=values))["data"]

    def insert(self, doc: dict) -> dict:
        return self._check(self.http.post(f"/api/resource/{doc['doctype']}", json=doc))["data"]

    def call(self, method: str, **params) -> Any:
        """A whitelisted ERPNext method (for example one that maps an invoice to a payment); returns its message."""
        return self._check(self.http.post(f"/api/method/{method}", json=params)).get("message")
