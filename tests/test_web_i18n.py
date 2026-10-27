"""The interface in two languages (ADR-0023): every English text the pages pass to t() has a Chinese translation,
with the same {placeholders}; no translation is empty. English is the key, so the English interface needs no table."""

import json
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "web" / "src"
ZH = json.loads((SRC / "locales" / "zh.json").read_text(encoding="utf-8"))

# t('…'), t("…"), t(`…`) with no ${…}; the first argument only
CALL = re.compile(r"""(?<![\w$.])t\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|`((?:[^`\\$]|\\.)*)`)""")
HOLE = re.compile(r"\{(\w+)\}")


def unescape(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


COMMENT = re.compile(r"(^|\s)//.*$", re.M)


def keys_in_source() -> dict[str, str]:
    found = {}
    for p in SRC.rglob("*"):
        if p.suffix not in (".vue", ".js") or "locales" in p.parts or ("help" in p.parts and p.suffix == ".md"):
            continue
        text = COMMENT.sub("", p.read_text(encoding="utf-8"))
        for m in CALL.finditer(text):
            k = unescape(next(g for g in m.groups() if g is not None))
            found.setdefault(k, str(p.relative_to(SRC)))
    return found


def test_every_text_has_chinese():
    missing = {k: f for k, f in keys_in_source().items() if k not in ZH}
    assert not missing, f"{len(missing)} texts without Chinese, e.g. {list(missing.items())[:10]}"


def test_translations_are_complete_and_keep_placeholders():
    for k, v in ZH.items():
        assert isinstance(v, str) and v.strip(), f"empty translation for {k!r}"
        assert set(HOLE.findall(k)) == set(HOLE.findall(v)), f"placeholders differ: {k!r} -> {v!r}"


def test_no_english_left_in_the_chinese_table():
    # a value that is the English key again was not translated; product names and codes may stay as they are
    same = [k for k, v in ZH.items() if k == v and re.search(r"[a-z]{3,} [a-z]{3,}", k)]
    assert not same, f"untranslated: {same[:10]}"
