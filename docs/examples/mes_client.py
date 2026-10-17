"""An example client for the WenQuest Ops machine interface (ADR-0020, 20d), with the Python standard library only.

    WQO_URL=https://ops.example.com WQO_TOKEN=wqo_... python mes_client.py events
    WQO_URL=... WQO_TOKEN=... python mes_client.py measurements IQC-00005 1 "Board thickness" 4.02

An MES or a gauge station would call these functions from its own code. What it sends waits in WenQuest Ops until a
person accepts it; events are read from where the last call stopped (keep ``next``).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):        # the token is never sent on to another address
        return None


_OPEN = urllib.request.build_opener(_NoRedirect).open


def call(base: str, token: str, method: str, path: str, body: dict | None = None, *, opener=_OPEN):
    """One call; returns (status, JSON). ``opener`` is replaceable for tests."""
    if not base.startswith("https://") and not base.startswith(("http://localhost", "http://127.0.0.1")):
        raise ValueError("the WenQuest Ops address starts with https:// (the token must not travel in clear)")
    req = urllib.request.Request(base.rstrip("/") + path, method=method,  # noqa: S310 - http(s) only, checked above
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"authorization": f"Bearer {token}", "content-type": "application/json"})
    try:
        with opener(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def send_measurements(base, token, inspection: str, readings: list[dict], equipment: str | None = None, **kw):
    """readings: [{"sample": 1, "characteristic": "Length", "value": 10.01}, ...]"""
    return call(base, token, "POST", "/api/integration/v1/measurements",
                {"inspection": inspection, "readings": readings, "equipment": equipment}, **kw)


def send_step(base, token, record: str, step: int, *, value=None, result=None, text=None, equipment=None, **kw):
    body = {"record": record, "step": step, "equipment": equipment}
    body |= {k: v for k, v in (("value", value), ("result", result), ("text", text)) if v is not None}
    return call(base, token, "POST", "/api/integration/v1/production-steps", body, **kw)


def events(base, token, after: int = 0, **kw):
    """Events after ``after``; keep the returned ``next`` for the next call."""
    return call(base, token, "GET", f"/api/integration/v1/events?after={int(after)}", **kw)


if __name__ == "__main__":
    url, tok = os.environ["WQO_URL"], os.environ["WQO_TOKEN"]
    what = sys.argv[1] if len(sys.argv) > 1 else "events"
    if what == "measurements":
        ins, sample, char, value = sys.argv[2], int(sys.argv[3]), sys.argv[4], float(sys.argv[5])
        print(send_measurements(url, tok, ins, [{"sample": sample, "characteristic": char, "value": value}]))
    else:
        print(events(url, tok, int(sys.argv[2]) if len(sys.argv) > 2 else 0))
