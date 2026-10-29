"""The help center (ADR-0019): every topic's head is well formed, its "Take me there" pages exist, its "Show me" steps
point at elements the pages really have, and every "What WenQuest Ops stops" line names a test that exists, so the
help cannot drift from the code unnoticed. Then the checklist progress kept per person."""

import re
from pathlib import Path

import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient

from tests.test_web import DEMO
from wqops.hub import accounts as Acc
from wqops.hub import db as DB
from wqops.hub import help_api as HA
from wqops.hub import permissions as P
from wqops.hub.app import create_app

ROOT = Path(__file__).resolve().parents[1]
HELP = ROOT / "web" / "src" / "help"
WEB = ROOT / "web" / "src"
GROUPS = re.findall(r"'([^']+)'", re.search(r"export const GROUPS = \[(.*?)\]",
                                              (HELP / "index.js").read_text()).group(1))
ROUTES = re.findall(r"path: '([^']+)'", (WEB / "main.js").read_text())
HOOKS = {m for p in WEB.rglob("*.vue") for m in re.findall(r'data-help="([a-z0-9-]+)"', p.read_text())}
PW = "Help pass 2026"


def topics():
    out = {}
    for p in sorted((HELP / "topics").glob("*.md")):
        m = re.match(r"^---\n(.*?)\n---\n", p.read_text(), re.S)
        assert m, f"{p.name}: no head"
        out[p.stem] = yaml.safe_load(m.group(1))
    return out


def routed(path: str) -> bool:
    path = re.split(r"[#?]", path, maxsplit=1)[0]
    return any(re.fullmatch(re.sub(r":\w+\??", "[^/]+", r) + "/?", path) for r in ROUTES)


def test_every_topic_is_well_formed():
    ts = topics()
    assert len(ts) >= 25 and {"getting-started", "management-reviews", "questions"} <= set(ts)
    for slug, t in ts.items():
        assert re.fullmatch(r"[a-z0-9-]+", slug), slug
        assert t["title"] and t["summary"] and isinstance(t["order"], int), slug
        assert t["group"] in GROUPS, (slug, t["group"])
        assert t.get("needs") in (None, *P.PERMISSIONS), slug
        if t.get("video"):
            assert (HELP / "media" / f"{t['video']}.webm").is_file(), (slug, t["video"])
        ids = [x["id"] for x in t.get("try", [])]
        assert len(ids) == len(set(ids)), slug
        for x in t.get("try", []):
            assert re.fullmatch(r"[a-z0-9-]{1,60}", x["id"]) and x["text"].strip(), (slug, x)
            assert set(x) <= {"id", "text", "to", "demo", "expect", "tour"}, (slug, x)
            assert not x.get("to") or routed(x["to"]), (slug, x["to"])
            assert not x.get("demo") or routed(x["demo"]), (slug, x["demo"])   # where the video shows it
            for s in x.get("tour", []):
                assert s["text"].strip(), (slug, s)
                assert set(s) <= {"target", "click", "text", "title", "path", "elsewhere"}, (slug, s)
                assert not s.get("path") or routed(s["path"]), (slug, s["path"])
                for sel in filter(None, (s["target"], s.get("click"))):
                    hook = re.fullmatch(r'\[data-help="([a-z0-9-]+)"\]', sel)
                    assert hook, f"{slug}: point Show me at a data-help element, not {sel}"
                    assert hook.group(1) in HOOKS, f"{slug}: no page has data-help={hook.group(1)}"
        for q in t.get("questions", []):
            assert q["q"].strip() and q["a"].strip(), slug


def test_what_it_stops_is_checked_by_a_test():
    for slug, t in topics().items():
        for b in t.get("blocks", []):
            assert b["text"].strip(), slug
            path, _, name = b["test"].partition("::")
            f = ROOT / path
            assert f.is_file() and path.startswith("tests/"), (slug, b["test"])
            assert re.search(rf"^def {re.escape(name)}\(", f.read_text(), re.M), (slug, b["test"])


def test_progress_is_kept_per_person(conn):
    assert HA.tick(conn, "jordan@demo.example", "risk/start", True) == {"risk/start": HA.progress(
        conn, "jordan@demo.example")["risk/start"]}
    HA.tick(conn, "jordan@demo.example", "risk/approve", True)
    assert set(HA.tick(conn, "jordan@demo.example", "risk/start", False)) == {"risk/approve"}
    assert HA.progress(conn, "dana@demo.example") == {}
    with pytest.raises(ValueError, match="not a checklist item"):
        HA.tick(conn, "jordan@demo.example", "Risk start", True)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        conn.execute("delete from help_progress")


def test_progress_api(db_url):
    c = TestClient(create_app({}, lambda: (DEMO, "ok"), db_url=db_url))
    c.__enter__()
    assert c.get("/api/help/progress").status_code == 401
    with DB.connect(db_url) as conn:
        Acc.sync(conn, DEMO)
        Acc.set_password(conn, "alex@demo.example", PW)
    c.post("/api/login", json={"email": "alex@demo.example", "password": PW})
    assert c.get("/api/help/progress").json() == {"done": {}}
    r = c.post("/api/help/progress", json={"item": "dashboard/open", "done": True})
    assert r.status_code == 200 and list(r.json()["done"]) == ["dashboard/open"]
    for bad in ({"item": "x"}, {"item": "a/b", "done": "yes"}, {"item": "../x", "done": True}, []):
        assert c.post("/api/help/progress", json=bad).status_code == 400, bad
    assert c.post("/api/help/progress", content=b"{", headers={"content-type": "application/json"}).status_code == 400
    c.__exit__(None, None, None)


def zh_topics():
    out = {}
    for p in sorted((HELP / "topics" / "zh").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        assert m, f"zh/{p.name}: no head"
        out[p.stem] = (yaml.safe_load(m.group(1)), text[m.end():])
    return out


def _shape(t: dict, body: str) -> dict:
    """What must be the same in both languages: the codes, the steps and where they go, the tours' elements, the
    tests behind "What WenQuest Ops stops", the number of questions and sections, the pictures and the links."""
    return {"keys": sorted(t), **{k: t.get(k) for k in ("group", "order", "needs", "video")},
            "try": [(x["id"], x.get("to"), x.get("demo"), sorted(x),
                     [(s["target"], s.get("click"), s.get("path"), "elsewhere" in s) for s in x.get("tour", [])])
                    for x in t.get("try", [])],
            "blocks": [b["test"] for b in t.get("blocks", [])], "questions": len(t.get("questions", [])),
            "sections": len(re.findall(r"^## ", body, re.M)),
            "images": re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body),
            "links": re.findall(r"\]\((/help/[^)]+|#[^)]+)\)", body)}


def test_every_topic_has_a_chinese_twin_with_the_same_steps():
    en = {p.stem: p.read_text(encoding="utf-8") for p in sorted((HELP / "topics").glob("*.md"))}
    zh = zh_topics()
    assert set(zh) == set(en), set(en) ^ set(zh)
    cjk = re.compile(r"[一-鿿]")
    for slug, text in en.items():
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        t_zh, body_zh = zh[slug]
        assert _shape(yaml.safe_load(m.group(1)), text[m.end():]) == _shape(t_zh, body_zh), slug
        assert cjk.search(t_zh["title"] + t_zh["summary"]) and cjk.search(body_zh), slug   # a title may be a code
        for x in t_zh.get("try", []):
            assert cjk.search(x["text"]), (slug, x["id"])
            for s in x.get("tour", []):
                assert cjk.search(s["text"]), (slug, x["id"], s["target"])
        for q in t_zh.get("questions", []):
            assert cjk.search(q["q"]) and cjk.search(q["a"]), slug


def test_the_chinese_help_names_the_chinese_demo():
    english_people = re.compile(r"\b(Dana|Jordan|Riley|Harbor Lane|Gulf Fasteners|Bayline|Coastal Packaging|"
                                r"Summit Tools)\b")
    for slug, (t, body) in zh_topics().items():
        text = yaml.safe_dump(t, allow_unicode=True) + body
        assert not english_people.search(text), (slug, english_people.search(text).group(0))
