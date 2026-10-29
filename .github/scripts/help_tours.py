"""Record a short video per help topic by playing its "Show me" tours on the demo company (ADR-0019 item 7).

    python help_tours.py https://ops.localtest.me dana@demo.example <password> <out dir> [topic ...]

For every topic with tours, the video opens the topic, then for each "Try it" step that has a tour goes to its page
(`demo:` when the step names a page of the freshly loaded demo, else `to:`), shows the step as a caption and plays the
tour with a moving pointer: the same tour a person gets from "Show me". Writes <out>/<topic>.webm.

It is also the check that the help still matches the pages: a tour step whose element is not found on the page the
step goes to fails the run (after every video is made, so one broken page does not hide the others), unless the step
says where else it is (`elsewhere`: the element only appears after an earlier step, such as a form being filled in);
such a step and the rest of its tour are left out of the video. Steps that only work on a page the tester opens
themselves (no `to` and no `demo`) are left out too.

HELP_FAST=1 plays the tours quickly without recording: the check alone, for every pull request.
HELP_LANG=zh plays the Chinese topics (web/src/help/topics/zh, ADR-0023) on a Chinese company; the tour's buttons are
found by their Chinese labels.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml
from playwright.sync_api import Page, sync_playwright

BASE, EMAIL, PASSWORD, OUT = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
ONLY = set(sys.argv[5:])
WEB = Path(__file__).resolve().parents[2] / "web" / "src"
LANG = os.environ.get("HELP_LANG", "en")
TOPICS = WEB / "help" / "topics" / ("zh" if LANG == "zh" else "")
_ZH = json.loads((WEB / "locales" / "zh.json").read_text(encoding="utf-8")) if LANG == "zh" else {}


def label(s: str) -> str:
    """A button's text in the interface's language."""
    return _ZH.get(s, s)
VIEW = {"width": 1280, "height": 800}
FAST = os.environ.get("HELP_FAST") == "1"
STEP_S = 0.2 if FAST else 3.2                  # how long each tour step stays on screen
PAUSE = 0.2 if FAST else 1.0

# a pointer that glides to whatever the tour highlights, and a caption bar for the "Try it" step
OVERLAY = """
(() => {
  try { localStorage.setItem('wqo-tour-done', '1') } catch (e) {}
  const add = () => {
    if (document.getElementById('wqo-pointer')) return
    const p = document.createElement('div'); p.id = 'wqo-pointer'
    p.style.cssText = 'position:fixed;z-index:60;width:22px;height:22px;border-radius:50%;left:50%;top:40%;' +
      'background:rgba(37,99,235,.35);border:2px solid #2563eb;pointer-events:none;' +
      'transition:left .7s cubic-bezier(.2,.8,.2,1),top .7s cubic-bezier(.2,.8,.2,1);transform:translate(-50%,-50%)'
    const c = document.createElement('div'); c.id = 'wqo-caption'
    c.style.cssText = 'position:fixed;z-index:60;left:50%;bottom:22px;transform:translateX(-50%);max-width:880px;' +
      'padding:10px 18px;border-radius:10px;background:rgba(17,24,39,.88);color:#fff;font:500 16px/1.45 system-ui,' +
      'sans-serif;pointer-events:none;display:none'
    document.body.append(p, c)
    new MutationObserver(() => {
      const el = document.querySelector('.tour-on')
      if (!el) return
      const r = el.getBoundingClientRect()
      p.style.left = `${Math.min(r.left + r.width / 2, innerWidth - 20)}px`
      p.style.top = `${Math.min(r.top + Math.min(r.height / 2, 40), innerHeight - 20)}px`
    }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] })
  }
  if (document.body) add(); else addEventListener('DOMContentLoaded', add)
})()
"""


def topics() -> dict[str, dict]:
    out = {}
    for p in sorted(TOPICS.glob("*.md")):
        m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
        out[p.stem] = yaml.safe_load(m.group(1)) if m else {}
    return out


def plain(s: str) -> str:
    return re.sub(r"[*_`]", "", s or "")


def caption(page: Page, text: str) -> None:
    page.evaluate("(t) => { const c = document.getElementById('wqo-caption'); if (c) { c.textContent = t; "
                  "c.style.display = t ? 'block' : 'none' } }", text)


def play(page: Page, slug: str, t: dict, misses: list[str]) -> int:
    page.goto(f"{BASE}/help/{slug}")
    page.wait_for_selector(".topic", timeout=30_000)
    time.sleep(PAUSE * 2.5)
    shown = 0
    for n, item in enumerate(t.get("try", []), start=1):
        where = item.get("demo") or item.get("to")
        if not item.get("tour") or not where:
            continue
        page.goto(f"{BASE}{where}")
        page.wait_for_load_state("networkidle", timeout=30_000)
        caption(page, f"{n}. {plain(item['text'])}")
        time.sleep(PAUSE * 1.2)
        steps = [{k: v for k, v in s.items() if k != "elsewhere"} for s in item["tour"]]
        page.evaluate("([s, name]) => window.wqoTour(s, name)", [steps, t["title"]])
        for k, s in enumerate(steps):
            page.wait_for_selector(".tour", timeout=10_000)
            found = False
            for _ in range(25):                          # the tour looks for the element for up to ~3 s
                time.sleep(0.2)
                if page.locator(".tour-on").count():
                    found = True
                    break
            if not found:
                if "elsewhere" not in item["tour"][k]:
                    misses.append(f"{slug}: step {n} ({item['id']}), tour {k + 1}: {s['target']} not on {where}")
                page.locator(".tour button", has_text=label("Close")).click()
                break
            time.sleep(STEP_S)
            page.locator(".tour button", has_text=label("Done" if k == len(steps) - 1 else "Next")).click()
        shown += 1
        caption(page, "")
    return shown


def shrink(raw: Path, dest: Path) -> None:
    """The browser's recording is large; VP9 at 12 frames a second keeps the text sharp at a fifth of the size."""
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found: keeping the raw recording", flush=True)
        shutil.move(raw, dest)
        return
    ffmpeg = shutil.which("ffmpeg")
    args = ["-v", "error", "-y", "-i", str(raw), "-an", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "45", "-row-mt",
            "1", "-deadline", "realtime", "-cpu-used", "8", "-r", "12", str(dest)]
    subprocess.run([ffmpeg, *args], check=True)  # noqa: S603 - fixed arguments on our own files


def main() -> int:
    out = OUT
    out.mkdir(parents=True, exist_ok=True)
    misses: list[str] = []
    made: dict[str, int] = {}
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("HELP_CHROME") or None)
        login = b.new_context(viewport=VIEW, ignore_https_errors=True)
        page = login.new_page()
        page.goto(f"{BASE}/login")
        page.fill("#email", EMAIL)
        page.fill("#password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url(f"{BASE}/", timeout=30_000)
        state = login.storage_state()
        login.close()
        for slug, t in topics().items():
            if (ONLY and slug not in ONLY) or not any(x.get("tour") for x in t.get("try", [])):
                continue
            d = out / f".rec-{slug}"
            rec = {} if FAST else {"record_video_dir": str(d), "record_video_size": VIEW}
            ctx = b.new_context(viewport=VIEW, ignore_https_errors=True, storage_state=state, **rec)
            ctx.add_init_script(OVERLAY)
            page = ctx.new_page()
            try:
                made[slug] = play(page, slug, t, misses)
            except Exception as exc:  # recorded as a miss; the other topics go on
                misses.append(f"{slug}: {exc}".splitlines()[0])
            finally:
                vid = page.video
                ctx.close()
                if vid:
                    shrink(Path(vid.path()), out / f"{slug}.webm")
                shutil.rmtree(d, ignore_errors=True)
            print("video", slug, made.get(slug), "tours", flush=True)
        b.close()
    print(json.dumps({"videos": made, "misses": misses}, indent=2))
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
