"""Screenshots and short videos of the main flows on the demo company (ADR-0012 item 7).

Runs a browser against an installed WenQuest Ops with the demo business loaded:

    python help_media.py https://ops.localtest.me dana@demo.example <password> <out dir>

Writes <out>/screens/*.png and <out>/videos/*.webm. Every page is checked for the element that shows it loaded;
a missing element fails the run after the remaining shots are taken, so one broken page does not hide the others.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE, EMAIL, PASSWORD, OUT = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
VIEW = {"width": 1280, "height": 800}
HOST = BASE.split("://", 1)[1].split("/")[0]
SPC_ITEM = os.environ.get("HELP_MEDIA_SPC_ITEM", "HX-BOLT-M8")   # the demo item whose readings drift
NO_TOUR = "try { localStorage.setItem('wqo-tour-done', '1') } catch (e) {}"
failures: list[str] = []


def sign_in(page: Page) -> None:
    page.goto(f"{BASE}/login")
    page.fill("#email", EMAIL)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url(f"{BASE}/", timeout=30_000)


def api(page: Page, path: str):
    r = page.request.get(f"{BASE}{path}")
    if not r.ok:
        raise RuntimeError(f"{path}: HTTP {r.status}")
    return r.json()


def go(page: Page, path: str, ready: str, pause: float = 0.6) -> None:
    page.goto(f"{BASE}{path}")
    page.wait_for_selector(ready, timeout=30_000)
    page.wait_for_load_state("networkidle")
    time.sleep(pause)


def shot(page: Page, name: str, path: str | None, ready: str, full: bool = False) -> None:
    try:
        if path is not None:
            go(page, path, ready)
        else:
            page.wait_for_selector(ready, timeout=30_000)
        page.screenshot(path=str(OUT / "screens" / f"{name}.png"), full_page=full)
        print("shot", name)
    except Exception as exc:  # report and continue with the next shot
        failures.append(f"{name}: {exc}".splitlines()[0])


def pick_option(page: Page, select: str, text: str) -> None:
    opts = page.locator(f"{select} option").all_inner_texts()
    idx = next((i for i, o in enumerate(opts) if text in o), None)
    if idx is None:
        raise RuntimeError(f"no option with {text!r} in {opts}")
    page.select_option(select, index=idx)


def facts(page: Page) -> dict:
    anoms = api(page, "/api/anomalies")
    late = next((a for a in anoms if a["rule"] == "order_late"), None)
    ncrs = api(page, "/api/quality/ncrs") or api(page, "/api/quality/ncrs?status=all")   # an open one if any
    capas = api(page, "/api/quality/capas?status=all")
    return {"late": late["id"] if late else None, "anomaly": anoms[0]["id"] if anoms else None,
            "ncr": ncrs[0]["id"] if ncrs else None, "capa": capas[0]["id"] if capas else None}


def screens(b) -> dict:
    ctx = b.new_context(viewport=VIEW, ignore_https_errors=True)
    ctx.add_init_script(NO_TOUR)
    page = ctx.new_page()
    sign_in(page)
    f = facts(page)
    print("facts", json.dumps(f))
    shot(page, "dashboard", "/", ".cards", full=True)
    shot(page, "anomalies", "/anomalies", "main table")
    if f["late"]:
        shot(page, "anomaly-late-order", f"/anomalies/{f['late']}", "h1", full=True)
    else:
        failures.append("no late-order anomaly in the demo data")
    shot(page, "objects", "/objects", ".search")
    shot(page, "drafts", "/drafts", "h1")
    try:
        go(page, "/assistant", ".search input")
        page.fill(".search input", "Which orders are late, and why?")
        page.click(".search button")
        page.wait_for_selector("article.turn", timeout=60_000)
        time.sleep(0.6)
        page.screenshot(path=str(OUT / "screens" / "assistant.png"))
        print("shot assistant")
    except Exception as exc:
        failures.append(f"assistant: {exc}".splitlines()[0])
    shot(page, "quality-ncrs", "/quality", "main table")
    if f["ncr"]:
        shot(page, "quality-ncr", f"/quality/ncr/{f['ncr']}", "h1", full=True)
    if f["capa"]:
        shot(page, "quality-capa", f"/quality/capa/{f['capa']}", "h1", full=True)
    shot(page, "quality-incoming", "/quality?tab=incoming", "main table")
    shot(page, "quality-suppliers", "/quality?tab=suppliers", "main table")
    try:
        go(page, "/quality?tab=spc", "select")
        pick_option(page, "select", SPC_ITEM)
        page.wait_for_selector("svg", timeout=30_000)
        time.sleep(0.8)
        page.screenshot(path=str(OUT / "screens" / "quality-spc.png"), full_page=True)
        print("shot quality-spc")
    except Exception as exc:
        failures.append(f"quality-spc: {exc}".splitlines()[0])
    document_shots(page)
    shot(page, "help", "/help/quality", ".help-nav")
    ctx.close()
    # the tour as a new user sees it (nothing remembered in this browser yet)
    ctx = b.new_context(viewport=VIEW, ignore_https_errors=True)
    page = ctx.new_page()
    sign_in(page)
    page.wait_for_selector(".cards", timeout=30_000)
    shot(page, "tour", None, ".tour-on")
    ctx.close()
    return f


def document_shots(page: Page) -> None:
    """The library and a proposal waiting for review (the demo folder is classified when the demo is loaded)."""
    shot(page, "documents", "/documents", "nav.tabs")
    docs = api(page, "/api/docs?status=to_review")
    pick = next((d for d in docs if d["doc_type"] == "procedure"), docs[0] if docs else None)
    if pick:
        shot(page, "document-review", f"/documents/{pick['id']}", "h1")
    else:
        failures.append("no document to review in the demo data")


def nav(page: Page, label: str) -> None:
    """Click a page in the sidebar."""
    page.locator('nav[aria-label="Main"]').get_by_role("link", name=label, exact=True).click()


def video(b, name: str, steps) -> None:
    d = OUT / "videos" / name
    ctx = b.new_context(viewport=VIEW, ignore_https_errors=True, record_video_dir=str(d), record_video_size=VIEW)
    page = ctx.new_page()
    try:
        if name != "tour":
            ctx.add_init_script(NO_TOUR)
        sign_in(page)
        steps(page)
        time.sleep(1.5)
    except Exception as exc:
        failures.append(f"video {name}: {exc}".splitlines()[0])
    finally:
        vid = page.video
        ctx.close()
        if vid:
            shutil.move(vid.path(), OUT / "videos" / f"{name}.webm")
        shutil.rmtree(d, ignore_errors=True)
        print("video", name)


def flow_late_order(f: dict):
    def run(page: Page) -> None:
        page.wait_for_selector(".cards")
        time.sleep(2)
        page.hover(".cards article >> nth=0")
        time.sleep(2)
        nav(page, "Anomalies")
        page.wait_for_selector("main table")
        time.sleep(2)
        if f["late"]:
            page.click(f"a[href='/anomalies/{f['late']}']")
            page.wait_for_selector("h1")
            time.sleep(4)
            page.mouse.wheel(0, 500)
            time.sleep(3)
    return run


def flow_assistant(page: Page) -> None:
    nav(page, "Assistant")
    page.wait_for_selector(".search input")
    time.sleep(1)
    page.type(".search input", "Which orders are late, and why?", delay=60)
    page.click(".search button")
    page.wait_for_selector("article.turn", timeout=60_000)
    time.sleep(4)
    page.click("article.turn summary")
    time.sleep(3)


def flow_quality(f: dict):
    def run(page: Page) -> None:
        nav(page, "Quality")
        page.wait_for_selector("main table")
        time.sleep(2)
        if f["ncr"]:
            page.click(f"a[href='/quality/ncr/{f['ncr']}']")
            page.wait_for_selector("h1")
            time.sleep(3)
            page.mouse.wheel(0, 600)
            time.sleep(2)
        if f["capa"]:
            page.goto(f"{BASE}/quality/capa/{f['capa']}")
            page.wait_for_selector("h1")
            time.sleep(3)
            page.mouse.wheel(0, 600)
            time.sleep(2)
        page.goto(f"{BASE}/quality?tab=incoming")
        page.wait_for_selector("main table")
        time.sleep(2)
        page.click("nav.tabs >> text=SPC")
        page.wait_for_selector("select")
        pick_option(page, "select", SPC_ITEM)
        page.wait_for_selector("svg")
        time.sleep(4)
    return run


def flow_tour(page: Page) -> None:
    page.wait_for_selector(".tour")
    for _ in range(10):
        time.sleep(2.5)
        nxt = page.locator(".tour button", has_text="Next")
        if not nxt.count():
            break
        nxt.click()
    page.locator(".tour button", has_text="Done").click()
    time.sleep(1)


def main() -> int:
    (OUT / "screens").mkdir(parents=True, exist_ok=True)
    (OUT / "videos").mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=[f"--host-resolver-rules=MAP {HOST} 127.0.0.1"])
        f = screens(b)
        video(b, "late-order", flow_late_order(f))
        video(b, "assistant", flow_assistant)
        video(b, "quality", flow_quality(f))
        video(b, "tour", flow_tour)
        b.close()
    for x in failures:
        print(f"::error title=help media::{x}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
