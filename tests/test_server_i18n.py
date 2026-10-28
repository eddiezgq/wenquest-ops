"""The hub's own texts in two languages (ADR-0023, step 23c): every say()/label() text in wqops has Chinese in
wqops/locales/zh.json with the same {placeholders}; the display texts of the process packs, the registers and the
ontology have Chinese; the language follows the request (cookie or header), else the company's."""

import ast
import json
import re
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from wqops import i18n as I18N
from wqops.company import ROLE_LABELS
from wqops.hub.app import create_app
from wqops.hub.permissions import PERMISSIONS
from wqops.i18n import say

ROOT = Path(__file__).resolve().parents[1]
ZH = json.loads((ROOT / "wqops" / "locales" / "zh.json").read_text(encoding="utf-8"))
WEB_ZH = json.loads((ROOT / "web" / "src" / "locales" / "zh.json").read_text(encoding="utf-8"))
HOLE = re.compile(r"\{(\w+)\}")
CALLS = {"say", "_say", "label"}
# display texts in the YAML configuration the hub sends to the page (identifiers, codes, synonyms are not)
YAML_FILES = [*sorted((ROOT / "wqops" / "hub" / "system" / "packs").glob("*.yaml")),
              *sorted((ROOT / "wqops" / "ontology").glob("*.yaml")),
              *sorted((ROOT / "wqops" / "ontology" / "rules").glob("*.yaml"))]
YAML_KEYS = {"label", "l", "summary", "hint", "inv", "source", "short", "name", "severity", "our_rule", "sign", "note"}


def keys_in_source() -> dict[str, str]:
    found = {}
    for p in (ROOT / "wqops").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not (isinstance(n, ast.Call) and n.args):
                continue
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            a = n.args[0]
            if name in CALLS and isinstance(a, ast.Constant) and isinstance(a.value, str):
                found.setdefault(a.value, str(p.relative_to(ROOT)))
    return found


def yaml_texts() -> dict[str, str]:
    out = {}

    def walk(o, where):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and k in YAML_KEYS:
                    out.setdefault(v, where)
                elif isinstance(v, dict) and k == "if_no":          # reasons a control point does not apply
                    out.update({r: where for r in v.values() if isinstance(r, str)})
                else:
                    walk(v, where)
        elif isinstance(o, list):
            for v in o:
                walk(v, where)

    for f in YAML_FILES:
        walk(yaml.safe_load(f.read_text(encoding="utf-8")), f.name)
    return out


def test_every_hub_text_has_chinese():
    missing = {k: f for k, f in keys_in_source().items() if k not in ZH}
    assert not missing, f"{len(missing)} hub texts without Chinese, e.g. {list(missing.items())[:10]}"


def test_every_configuration_text_has_chinese():
    missing = {k: f for k, f in yaml_texts().items() if k not in ZH}
    assert not missing, f"{len(missing)} configuration texts without Chinese, e.g. {list(missing.items())[:10]}"


def test_permission_names_have_chinese():
    assert not [v for v in [*PERMISSIONS.values(), *ROLE_LABELS.values()] if v not in ZH]


def test_register_choices_are_shown_in_chinese_on_the_page():
    regs = yaml.safe_load((ROOT / "wqops" / "hub" / "system" / "packs" / "registers.yaml").read_text("utf-8"))
    choices = {c for r in regs["registers"].values() for f in r["fields"].values() for c in f.get("choices") or ()}
    assert choices and not [c for c in choices if f"choice::{c}" not in WEB_ZH]


def test_translations_are_complete_and_keep_placeholders():
    for k, v in ZH.items():
        assert isinstance(v, str) and v.strip(), f"empty translation for {k!r}"
        assert set(HOLE.findall(k)) == set(HOLE.findall(v)), f"placeholders differ: {k!r} -> {v!r}"
    same = [k for k, v in ZH.items() if k == v and re.search(r"[a-z]{3,} [a-z]{3,}", k)]
    assert not same, f"untranslated: {same[:10]}"


def test_say_follows_the_language():
    with I18N.use("en"):
        assert say("{n} day", n=1) == "1 day"
        assert say("status::Open") == "Open"
        assert say("a text nobody translated {x}", x=2) == "a text nobody translated 2"
    with I18N.use("zh"):
        assert say("not found") == ZH["not found"]
        assert say("a text nobody translated {x}", x=2) == "a text nobody translated 2"
        assert I18N.label("Training and competence") == ZH["Training and competence"]
        assert I18N.label("Harbor Lane Supply") == "Harbor Lane Supply"     # data stays as it is
        assert I18N.localize({"label": "Training and competence", "key": "training"}) == {
            "label": ZH["Training and competence"], "key": "training"}


def test_language_names():
    assert I18N.norm("zh-CN") == "zh" and I18N.norm("en_US") == "en" and I18N.norm("fr") is None


def test_a_request_gets_the_hub_texts_in_its_language():
    company = {"company": {"name": "Demo", "language": "en"}}
    app = create_app(checks={}, company=lambda: (company, "ok"), db_url="")
    c = TestClient(app)
    detail = lambda **kw: c.get("/api/sync/status", **kw).json()["detail"]  # noqa: E731 - no database configured
    assert detail() == "the hub database is not configured"
    assert detail(headers={"x-wqo-lang": "zh"}) == ZH["the hub database is not configured"]
    c.cookies.set(I18N.COOKIE, "zh")
    assert detail() == ZH["the hub database is not configured"]
    assert detail(headers={"x-wqo-lang": "en"}) == "the hub database is not configured"
    c.cookies.clear()
    # without a choice, the company's language
    zh_company = {"company": {"name": "Demo", "language": "zh"}}
    c2 = TestClient(create_app(checks={}, company=lambda: (zh_company, "ok"), db_url=""))
    try:
        assert c2.get("/api/sync/status").json()["detail"] == ZH["the hub database is not configured"]
    finally:
        I18N.set_company_language("en")


def test_the_sign_in_page_follows_the_language():
    app = create_app(checks={}, company=lambda: (None, "not configured"), db_url="")
    c = TestClient(app)
    en = c.get("/login").text
    zh = c.get("/login", headers={"x-wqo-lang": "zh"}).text
    assert "<html lang='en'" in en and "lang='zh-CN'" in zh and en != zh
