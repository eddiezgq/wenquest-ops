"""Phase 1 acceptance smoke test in a browser (plan item 10): every role on every page it may open, and the main
flows end to end on the installed system with the demo business loaded.

    python smoke_p1.py https://ops.localtest.me <owner email> <owner password>

1. The owner sets a password for each demo person on the People page (the install sets only the owner's).
2. Each role signs in, opens every page in its menu without a script error, sees Quality only if allowed, and is
   refused the APIs it may not use; the People page only for those who may see users. One person changes their
   own password on My account and signs in with it.
3. Purchasing drafts a replenishment purchase order from an item page and confirms it: it is created in ERPNext.
4. Sales drafts a delay message for a late order and confirms it.
5. Quality drafts an incoming inspection for the receipt waiting for one and confirms it: created in ERPNext.
6. Quality opens a nonconformance, contains it and submits "use as is"; the operations manager approves it with
   their password (someone else must); Quality closes it with theirs. Two signatures are recorded.
7. Documents (ADR-0014): the demo folder was imported and classified; Quality uploads a procedure on the Documents
   page, classifies it, confirms it and sends it for approval; the operations manager approves it with their
   password and it becomes effective. The checks list the demo folder's problems; Quality keeps the older revision
   of a procedure as obsolete from the Problems tab.
"""

from __future__ import annotations

import importlib.util
import sys
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

BASE, OWNER, OWNER_PW = sys.argv[1], sys.argv[2], sys.argv[3]
HOST = BASE.split("://", 1)[1].split("/")[0]
PW = "Smoke pass 2026"
NO_TOUR = "try { localStorage.setItem('wqo-tour-done', '1') } catch (e) {}"
spec = importlib.util.spec_from_file_location(
    "permissions", Path(__file__).resolve().parents[2] / "wqops" / "hub" / "permissions.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        failures.append(what)


class Session:
    def __init__(self, b: Browser, email: str, password: str):
        self.ctx = b.new_context(viewport={"width": 1280, "height": 800}, ignore_https_errors=True)
        self.ctx.add_init_script(NO_TOUR)
        self.page = self.ctx.new_page()
        self.errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        p = self.page
        p.goto(f"{BASE}/login")
        p.fill("#email", email)
        p.fill("#password", password)
        p.click("button[type=submit]")
        p.wait_for_url(f"{BASE}/", timeout=30_000)
        p.wait_for_selector('nav[aria-label="Main"]', timeout=30_000)
        self.me = self.get("/api/me")

    def get(self, path: str):
        r = self.page.request.get(f"{BASE}{path}")
        if not r.ok:
            raise RuntimeError(f"GET {path}: HTTP {r.status} {r.text()[:200]}")
        return r.json()

    def status(self, path: str) -> int:
        return self.page.request.get(f"{BASE}{path}").status

    def post(self, path: str, body: dict):
        r = self.page.request.post(f"{BASE}{path}", data=body)
        if not r.ok:
            raise RuntimeError(f"POST {path}: HTTP {r.status} {r.text()[:200]}")
        return r.json()

    def go(self, path: str, ready: str = "h1") -> Page:
        self.page.goto(f"{BASE}{path}")
        self.page.wait_for_selector(ready, timeout=30_000)
        self.page.wait_for_load_state("networkidle")
        return self.page

    def close(self) -> None:
        self.ctx.close()


def step(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:  # report and go on with the other flows
        check(False, f"{name}: {str(exc).splitlines()[0]}")


def roles(b: Browser, people: list[dict]) -> None:
    for u in people:
        s = Session(b, u["email"], OWNER_PW if u["email"] == OWNER else PW)
        perms = P.of(u["roles"])
        nav = s.page.locator('nav[aria-label="Main"] a').all_inner_texts()
        check(("Quality" in nav) == ("quality:view" in perms), f"{u['email']}: Quality in the menu only if allowed")
        for path in ["/", "/assistant", "/anomalies", "/objects", "/drafts", "/help", "/documents"] + \
                (["/quality", "/quality?tab=incoming", "/quality?tab=suppliers", "/quality?tab=spc"]
                 if "quality:view" in perms else []):
            try:
                s.go(path, "h1, main .help-nav")
            except Exception as exc:
                check(False, f"{u['email']}: {path} did not load ({str(exc).splitlines()[0]})")
        check(("People" in nav) == ("users:view" in perms), f"{u['email']}: People in the menu only if allowed")
        if "users:view" in perms:
            try:
                s.go("/people", "main table")
            except Exception as exc:
                check(False, f"{u['email']}: /people did not load ({str(exc).splitlines()[0]})")
        s.go("/documents", "nav.tabs")
        check((s.page.locator("section.drop").count() > 0) == ("documents:edit" in perms),
              f"{u['email']}: may upload documents only if allowed")
        s.go("/account", "h1")
        check(not s.errors, f"{u['email']}: no script errors ({s.errors[:2]})")
        if "quality:view" not in perms:
            check(s.status("/api/quality/ncrs") == 403, f"{u['email']}: quality API refused")
        if "users:view" not in perms:
            check(s.status("/api/users") == 403, f"{u['email']}: user list refused")
        s.close()


def set_passwords(owner: Session, people: list[dict]) -> None:
    p = owner.go("/people", "main table")
    for u in people:
        if u["email"] == OWNER:
            continue
        row = p.locator("main table tbody tr", has_text=u["email"])
        row.locator("input[type=password]").fill(PW)
        row.get_by_role("button", name="Set").click()
        p.wait_for_selector(f"text=Password set for {u['name']}", timeout=30_000)
    now = {x["email"]: x for x in owner.get("/api/users")}
    check(all(now[u["email"]]["has_password"] for u in people), "owner: passwords set on the People page")


def own_password(b: Browser) -> None:
    s = Session(b, "riley@demo.example", PW)
    p = s.go("/account", "h1")
    p.fill("input[placeholder='Current password']", PW)
    p.fill("input[placeholder='New password']", "Riley changed 2026")
    p.fill("input[placeholder='New password again']", "Riley changed 2026")
    p.get_by_role("button", name="Save password").click()
    p.wait_for_url("**/login**", timeout=30_000)
    s.close()
    again = Session(b, "riley@demo.example", "Riley changed 2026")
    check(again.me["email"] == "riley@demo.example", "riley: changed own password on My account and signed in")
    again.close()


def confirm_newest(s: Session, doctype: str) -> dict:
    """Confirm the newest pending draft of ``doctype`` on the Drafts page; return it as the API sees it after."""
    s.go("/drafts", "h1")
    s.page.wait_for_selector("article.draft", timeout=30_000)
    card = s.page.locator("article.draft", has_text=doctype).filter(has_text="pending").first
    card.get_by_role("button", name="Confirm").click()
    d = None
    for _ in range(60):
        d = next(x for x in s.get("/api/erp/drafts") if x["doctype"] == doctype)
        if d["status"] not in ("pending", "confirming"):   # confirming: ERPNext is still answering
            break
        time.sleep(1)
    return d


def purchasing(b: Browser) -> None:
    s = Session(b, "pat@demo.example", PW)
    short = [a for a in s.get("/api/anomalies") if a["rule"] == "item_short"]
    check(bool(short), "purchasing: sees short items")
    item = short[0]["subject"][1]
    s.go(f"/o/Item/{urllib.parse.quote(item, safe='')}", "h1")
    s.page.get_by_role("button", name="Draft a replenishment purchase order").click()
    s.page.wait_for_url(f"{BASE}/drafts", timeout=60_000)
    d = confirm_newest(s, "Purchase Order")
    check(d["status"] == "confirmed" and bool(d.get("erp_name")),
          f"purchasing: purchase order for {item} confirmed into ERPNext ({d.get('erp_name')}, {d.get('error')})")
    s.close()


def sales(b: Browser) -> None:
    s = Session(b, "alex@demo.example", PW)
    late = [a for a in s.get("/api/anomalies") if a["rule"] == "order_late"]
    check(bool(late), "sales: sees late orders")
    if not late:
        return
    key = late[0]["subject"][1]
    s.go(f"/o/SalesOrder/{urllib.parse.quote(key, safe='')}", "h1")
    s.page.get_by_role("button", name="Draft a delay message to the customer").click()
    s.page.wait_for_url(f"{BASE}/drafts", timeout=60_000)
    d = confirm_newest(s, "Customer Message")
    check(d["status"] == "confirmed", f"sales: delay message for {key} confirmed ({d.get('error')})")
    s.page.select_option('select[aria-label="Show"]', "confirmed")
    s.page.wait_for_selector("article.draft", timeout=30_000)
    check(s.page.get_by_role("button", name="Copy to send").count() > 0, "sales: message ready to copy")
    s.close()


def incoming(b: Browser) -> None:
    s = Session(b, "jordan@demo.example", PW)
    p = s.go("/quality?tab=incoming", "main table")
    row = p.locator("main table tbody tr").first
    row.locator("input").fill("5")
    row.get_by_role("button", name="Draft inspection").click()
    p.wait_for_url(f"{BASE}/drafts", timeout=60_000)
    d = confirm_newest(s, "Quality Inspection")
    check(d["status"] == "confirmed" and bool(d.get("erp_name")),
          f"quality: incoming inspection confirmed into ERPNext ({d.get('erp_name')}, {d.get('error')})")
    s.close()


def nonconformance(b: Browser) -> None:
    q = Session(b, "jordan@demo.example", PW)
    p = q.go("/quality", "h1")
    p.get_by_role("button", name="New nonconformance").click()
    p.fill("form.form input[placeholder=Title]", "Smoke test: dented boxes")
    p.fill("form.form textarea", "3 shipping boxes dented in the warehouse.")
    p.fill("form.form input[placeholder='Item code (optional)']", "BOX-12")
    p.fill("form.form input[placeholder=Quantity]", "3")
    p.get_by_role("button", name="Open the report").click()
    p.wait_for_url("**/quality/ncr/*", timeout=30_000)
    url = p.url
    p.fill("input[placeholder^='e.g. lot moved']", "Boxes set aside")
    p.get_by_role("button", name="Save containment").click()
    p.wait_for_selector("text=Submit disposition")
    p.select_option("select", "use_as_is")
    p.fill("input[placeholder=Quantity]", "3")
    p.fill("input[placeholder=Reason]", "Dents are cosmetic; boxes still close")
    p.get_by_role("button", name="Submit disposition").click()
    p.wait_for_selector("text=someone else must approve it")
    m = Session(b, "sam@demo.example", PW)
    mp = m.go(urllib.parse.urlparse(url).path, "h1")
    mp.fill("input[placeholder='Your password to sign'] >> nth=0", PW)
    mp.get_by_role("button", name="Approve (sign)").click()
    mp.wait_for_selector("text=Close (sign)")
    m.close()
    p.reload()
    p.wait_for_selector("text=Close (sign)")
    p.fill("input[placeholder='Closing note']", "Released for use")
    p.fill("input[placeholder='Your password to sign'] >> nth=0", PW)
    p.get_by_role("button", name="Close (sign)").click()
    p.wait_for_selector("text=Close (sign)", state="detached", timeout=30_000)
    n = q.get(f"/api/quality/ncrs/{url.rstrip('/').split('/')[-1]}")
    check(n["status"] == "closed" and len(n["signatures"]) >= 2,
          f"quality: NCR approved by someone else and closed, {len(n['signatures'])} signatures")
    check(not q.errors, f"quality: no script errors ({q.errors[:2]})")
    q.close()


def wait_import(s: Session, imp_id: int, want: str) -> dict:
    for _ in range(120):
        imp = s.get(f"/api/docs/imports/{imp_id}")
        if imp["status"] == want:
            return imp
        time.sleep(1)
    raise RuntimeError(f"import {imp_id} is still {imp['status']}, not {want}")


def documents(b: Browser) -> None:
    q = Session(b, "jordan@demo.example", PW)
    demo = [i for i in q.get("/api/docs/imports") if i["label"].startswith("Demo:")]
    check(bool(demo) and demo[0]["files"] >= 18 and demo[0]["status"] == "done",
          f"documents: demo folder imported and classified ({demo[0]['files'] if demo else 0} files)")
    p = q.go("/documents", "section.drop")
    body = (b"Harbor Lane Supply (Demo) - Quality procedure\nDoc No.: QP-14    Rev: A    Effective date: 2026-10-01\n"
            b"Handling of Customer Complaints\nDocument owner: Quality Manager\n1. Purpose\nTo answer every customer "
            b"complaint within 5 working days.\n2. Records\n- F-QA-030 Complaint Log\n")
    p.locator("section.drop input[type=file]:not([webkitdirectory])").set_input_files(
        [{"name": "QP-14 Customer Complaints Rev A.txt", "mimeType": "text/plain", "buffer": body}])
    p.get_by_role("button", name="Upload").click()
    p.wait_for_selector("text=Uploaded.", timeout=60_000)
    imp = q.get("/api/docs/imports")[0]
    wait_import(q, imp["id"], "ready")
    p = q.go("/documents?tab=imports", "nav.tabs")
    ai = q.get("/api/docs/meta")["ai"]
    p.get_by_role("button", name="Classify with AI" if ai else "Classify with rules").first.click()
    wait_import(q, imp["id"], "done")
    (d,) = q.get(f"/api/docs?status=to_review&import_id={imp['id']}")
    check(d["doc_type"] == "procedure" and d["process"] == "complaints" and d["number"] == "QP-14",
          f"documents: classified by {d['engine']} as {d['doc_type']} / {d['process']} / {d['number']}")
    p = q.go(f"/documents/{d['id']}", "h1")
    p.get_by_role("button", name="Confirm").click()
    p.get_by_role("button", name="Send for approval").click()
    p.wait_for_selector("text=someone else approves it", timeout=30_000)
    m = Session(b, "sam@demo.example", PW)
    mp = m.go(f"/documents/{d['id']}", "h1")
    mp.fill("input[placeholder='Your password to sign']", PW)
    mp.get_by_role("button", name="Approve (sign)").click()
    mp.wait_for_selector("text=The document is effective", timeout=30_000)
    after = m.get(f"/api/docs/{d['id']}")
    check(after["status"] == "effective" and after["fingerprint"] == after["sha256"] and len(after["signatures"]) == 1,
          f"documents: procedure approved by someone else and effective ({after['status']})")
    found = q.get("/api/docs/issues")
    kinds = {i["kind"] for i in found["issues"]}
    check({"duplicate", "revisions", "missing_ref"} <= kinds, f"documents: checks find the demo problems ({kinds})")
    rev = next((i for i in found["issues"] if i["kind"] == "revisions"), None)
    if rev:
        p = q.go("/documents?tab=problems", "article.issue")
        p.locator("article.issue", has_text=rev["title"]).get_by_role("button", name="Keep as obsolete").first.click()
        p.wait_for_selector("text=Kept as obsolete.", timeout=30_000)
        old = q.get(f"/api/docs/{rev['older'][0]}")
        check(old["status"] == "obsolete", f"documents: older revision kept as obsolete ({old['status']})")
    check(not q.errors and not m.errors, f"documents: no script errors ({(q.errors + m.errors)[:2]})")
    m.close()
    q.close()


def main() -> int:
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=[f"--host-resolver-rules=MAP {HOST} 127.0.0.1"])
        owner = Session(b, OWNER, OWNER_PW)
        people = owner.get("/api/users")
        step("people page", lambda: set_passwords(owner, people))
        owner.close()
        step("roles", lambda: roles(b, people))
        step("my account", lambda: own_password(b))
        step("purchasing", lambda: purchasing(b))
        step("sales", lambda: sales(b))
        step("incoming inspection", lambda: incoming(b))
        step("nonconformance", lambda: nonconformance(b))
        step("documents", lambda: documents(b))
        b.close()
    for f in failures:
        print(f"::error title=Phase 1 smoke::{f}")
    print(f"{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
