"""Texts the hub writes, in the reader's language (ADR-0023, step 23c).

English is the source text and the key, as in the web pages (web/src/i18n.js); Chinese comes from
``wqops/locales/zh.json``. ``say("{name} is on hold", name=lot)`` gives the text in the current language:

- during a request, the language the person chose in the web workspace (cookie ``wqo-lang``), otherwise the company's;
- outside a request (background sync, anomaly detection, the command line), the company's (manifest ``language``).

A text with no Chinese yet stays English, and tests/test_server_i18n.py fails, so new texts are translated in the same
change. ``say("status::Open")``: the same English word with another meaning gets its own Chinese; the part before ``::``
is not shown. Placeholders are ``{word}`` only; numbers are formatted before they are passed in.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path

LANGS = ("en", "zh")
COOKIE = "wqo-lang"
CATALOG_DIR = Path(__file__).resolve().parent / "locales"
_HOLE = re.compile(r"\{(\w+)\}")
_request: contextvars.ContextVar[str | None] = contextvars.ContextVar("wqo_lang", default=None)
_company = {"lang": "en"}


@cache
def table(lang: str) -> dict[str, str]:
    if lang == "en":
        return {}
    return json.loads((CATALOG_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def norm(lang: str | None) -> str | None:
    """'zh', 'zh-CN', 'zh-Hans' -> 'zh'; 'en-US' -> 'en'; anything else -> None."""
    if not lang:
        return None
    base = lang.strip().lower().replace("_", "-").split("-")[0]
    return base if base in LANGS else None


def set_company_language(lang: str | None) -> None:
    _company["lang"] = norm(lang) or "en"


def company_language() -> str:
    return _company["lang"]


def current() -> str:
    return _request.get() or _company["lang"]


@contextlib.contextmanager
def use(lang: str | None) -> Iterator[None]:
    """Write in ``lang`` inside the block (documents in the company's language, tests)."""
    tok = _request.set(norm(lang))
    try:
        yield
    finally:
        _request.reset(tok)


def _fill(text: str, params: dict) -> str:
    if not params:
        return text
    return _HOLE.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), text)


def say(text: str, /, **params) -> str:
    """``text`` in the current language with ``{placeholders}`` filled in."""
    lang = current()
    out = table(lang).get(text) if lang != "en" else None
    if out is None:
        i = text.find("::")
        out = text[i + 2:] if i > 0 else text
    return _fill(out, params)


def label(text: str | None) -> str | None:
    """A fixed name the hub sends (a permission, a register field): its translation when there is one, else as is."""
    if not text or not isinstance(text, str):
        return text
    return say(text) if text in table(current()) or "::" in text else text


class LanguageMiddleware:
    """Pure ASGI middleware: the request's language from the header X-WQO-Lang, else the cookie wqo-lang, else the
    company's. The browser's Accept-Language is not used on purpose: the company's language is the default."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        header = cookie = None
        for k, v in scope.get("headers") or ():
            if k == b"x-wqo-lang":
                header = norm(v.decode("latin-1"))
            elif k == b"cookie":
                for part in v.decode("latin-1").split(";"):
                    name, _, val = part.strip().partition("=")
                    if name == COOKIE:
                        cookie = norm(val)
        tok = _request.set(header or cookie)
        try:
            return await self.app(scope, receive, send)
        finally:
            _request.reset(tok)


LABEL_KEYS = frozenset({"label", "hint", "summary", "note", "question", "requirement", "what", "how"})


def localize(obj, keys: frozenset[str] | set[str] = LABEL_KEYS):
    """A copy of configuration data (a process pack, a register, the ontology) with the fixed texts under ``keys``
    translated where the catalog has them. Only for data the hub defines, never for records people wrote, and only on
    the way out: what is stored, hashed or adopted stays English."""
    if current() == "en":
        return obj
    if isinstance(obj, dict):
        return {k: (label(v) if k in keys and isinstance(v, str) else localize(v, keys)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [localize(v, keys) for v in obj]
    return obj
