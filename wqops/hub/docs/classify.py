"""Classification of imported files (ADR-0014 item 3): the shape of a proposal, the check that its quotes are really
in the file, and the rule-based fallback used when no model is available ("rules, limited accuracy").

A proposal is a dict of field values plus ``evidence``: for each field the sentence of the file it rests on and
whether code found that sentence in the file. Unverified fields are shown as such and keep a document out of the
batch confirmation. Plain code: no AI, no network.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

TYPES = {"procedure": "Procedure", "work_instruction": "Work instruction", "form": "Form or template",
         "record": "Record", "spec": "Specification or drawing", "certificate": "Certificate",
         "external": "External document", "other": "Other"}
CONTROLLED = {"procedure", "work_instruction", "form"}      # need signed approval to become effective
FIELDS = ("doc_type", "process", "number", "title", "revision", "effective_date", "owner", "language")
QUOTED = ("doc_type", "process", "number", "title", "revision", "effective_date", "owner")
CORE = ("doc_type", "process", "title")                    # a high-confidence proposal has these verified
LEVELS = ("high", "medium", "low")

_DASH = dict.fromkeys(map(ord, "‐‑‒–—−"), "-") | dict.fromkeys(
    map(ord, "‘’‚‛"), "'") | dict.fromkeys(map(ord, "“”„"), '"')


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).translate(_DASH).replace("_", " ").lower()
    return re.sub(r"\s+", " ", s).strip()


def corpus(name: str, path: str, text: str) -> str:
    """What a quote may come from: the file name, its folder path and its text."""
    return norm(f"{path}/{name}\n{text}")


def _value_in_quote(field: str, value, quote: str) -> bool:
    q = norm(quote)
    if field in ("number", "revision", "owner"):                # as a whole word: revision "C" is not in "Doc"
        return re.search(rf"(?<![a-z0-9]){re.escape(norm(value))}(?![a-z0-9])", q) is not None
    if field == "title":
        v = norm(value)
        return v in q or (q in v and len(q) >= 0.6 * len(v))
    if field == "effective_date":
        d = value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
        return any(d == x for x in dates_in(quote))
    return True


def verify(proposal: dict, name: str, path: str, text: str) -> dict:
    """Check every quote against the file and every value against its quote; set ``verified`` per field and cap the
    confidence: a proposal whose core fields are not all verified is not ``high``."""
    body = corpus(name, path, text)
    ev = {}
    for f in QUOTED:
        if proposal.get(f) in (None, ""):
            continue
        quote = str((proposal.get("evidence") or {}).get(f, {}).get("quote") or "").strip()
        ok = len(norm(quote)) >= 3 and norm(quote) in body
        try:
            ok = ok and _value_in_quote(f, proposal[f], quote)
        except ValueError:
            ok = False
        ev[f] = {"quote": quote[:400], "verified": ok}
    refs, dropped = [], []
    for r in proposal.get("refs") or []:
        (refs if norm(r) and norm(r) in body else dropped).append(r)
    out = dict(proposal, evidence=ev, refs=refs[:50])
    if dropped:
        out["refs_unverified"] = dropped[:50]
    conf = proposal.get("confidence") if proposal.get("confidence") in LEVELS else "low"
    if conf == "high" and not all(ev.get(f, {}).get("verified") for f in CORE):
        conf = "medium"
    out["confidence"] = conf
    return out


def batch_ok(doc: dict) -> bool:
    """May be confirmed with others in one step: high confidence and every quoted field verified."""
    ev = doc.get("evidence") or {}
    return doc.get("confidence") == "high" and all(ev.get(f, {}).get("verified") for f in CORE) and \
        all(v.get("verified") for v in ev.values())


# ---------------------------------------------------------------- dates

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                       "dec"], 1)}
_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_US = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MDY = re.compile(r"\b([A-Za-z]{3,9})\.? (\d{1,2}),? (\d{4})\b")
_DMY = re.compile(r"\b(\d{1,2}) ([A-Za-z]{3,9})\.? (\d{4})\b")


def dates_in(s: str) -> list[dt.date]:
    out = []

    def add(y, m, d):
        try:
            out.append(dt.date(int(y), int(m), int(d)))
        except (TypeError, ValueError):
            pass

    for y, m, d in _ISO.findall(s):
        add(y, m, d)
    for m, d, y in _US.findall(s):
        add(y, m, d)
    for mon, d, y in _MDY.findall(s):
        add(y, _MONTHS.get(mon[:3].lower()), d)
    for d, mon, y in _DMY.findall(s):
        add(y, _MONTHS.get(mon[:3].lower()), d)
    return out


# ---------------------------------------------------------------- rules

_TYPE_RULES = [
    ("certificate", r"\bcertificate\b|\bcertification\b|\bcert\b|\bcertificate of conformance\b"),
    ("work_instruction", r"\bwork instruction|\bwi[-_ ]\d|\bwi[-_][a-z]"),
    ("procedure", r"\bprocedure\b|\bsop\b|\bqp[-_ ]\d|\bqp[-_][a-z]"),
    ("form", r"\bform\b|\btemplate\b|\bchecklist\b|(^|/)f[-_][a-z0-9]"),
    ("spec", r"\bspecification\b|\bdrawing\b|\bspec\b|\bdatasheet\b"),
    ("record", r"\brecord\b|\blog\b|\bregister\b|\breport\b|\bminutes\b|\bresults\b"),
    ("external", r"\biso \d{4,5}\b|\bastm\b|\bregulation\b|\bstandard\b"),
]
_PROCESS_RULES = {
    "document_control": r"document control|control of documents|documents and records",
    "training": r"training|competenc",
    "purchasing": r"purchas|supplier|vendor",
    "receiving": r"receiving|incoming inspection|goods receipt|receipt inspection",
    "production": r"production|assembly|manufactur|work order",
    "nonconformance": r"nonconform|non-conform|\bncr\b",
    "capa": r"corrective|preventive|\bcapa\b",
    "calibration": r"calibrat|\bgauges?\b|\bgages?\b",
    "complaints": r"complaint|customer feedback|\brma\b|customer return",
    "internal_audit": r"internal audit|audit program|audit plan",
    "management_review": r"management review",
}
_LABEL_NO = re.compile(r"(?:doc(?:ument)?\.?\s*(?:no|number|#)|form\s*(?:no|number))\.?\s*[:#]?\s*"
                       r"([A-Za-z0-9][A-Za-z0-9._/-]{1,30})", re.IGNORECASE)
_CODE = re.compile(r"\b[A-Z]{1,5}(?:-[A-Z0-9]{1,6}){1,3}\b")
_REV = re.compile(r"\brev(?:ision)?\.?\s*[:#]?\s*([A-Z]|\d{1,2}(?:\.\d{1,2})?)\b", re.IGNORECASE)
_EFFECTIVE = re.compile(r"effective(?:\s+date)?\s*:?\s*([^\n|]{6,30})", re.IGNORECASE)
_OWNER = re.compile(r"(?:process owner|document owner|owner|prepared by|author)\s*:\s*([^\n|]{2,60})", re.IGNORECASE)
_TITLE = re.compile(r"(?:^|\n)\s*title\s*:\s*([^\n|]{3,120})", re.IGNORECASE)


def _line(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:end if end >= 0 else len(text)].strip()


def _where(rx: str | None, label: str, title: str, head: str) -> str:
    """The text a rule matched in: the file path, the title, or the line of the file."""
    if rx is None:
        return label
    for s in (label, title):
        if re.search(rx, norm(s)):
            return s
    m = re.search(rx, head, re.IGNORECASE)
    return _line(head, m.start()) if m else label


_STOP = {"rev", "revision", "the", "and", "of", "for", "a", "to", "copy", "final", "draft", "new", "old", "doc"}


def _title(stem: str, head: str) -> tuple[str, str]:
    """(title, quote): among the first lines, the one sharing most words with the file name (without its number and
    revision); else the file name. Page headers ("Company - Quality procedure") rarely match the file name."""
    name = re.sub(r"\brev(?:ision)?[.\s_-]*(?:[a-z]|\d[\d.]*)\b", " ", stem, flags=re.IGNORECASE)
    for c in _codes(name):
        name = name.replace(c, " ")
    name = re.sub(r"[\s_]+", " ", name).strip(" -")
    words = {w for w in re.findall(r"[a-z]{3,}", name.lower())} - _STOP
    best, score = None, (min(2, len(words)), -999)
    for raw in head.splitlines()[:15]:
        ln = raw.strip().lstrip("#").strip()
        if not 4 <= len(ln) <= 120 or "|" in ln or ln.startswith(("Sheet:", "-", "•")) or _LABEL_NO.search(ln) \
                or _REV.search(ln) or _codes(ln):                # list items and lines naming other documents
            continue
        lw = re.findall(r"[a-z]{3,}", ln.lower())
        hit = (len(words & set(lw)), -len(lw))        # most shared words; on a tie the shorter line
        if hit[0] >= score[0] and hit > score:
            best, score = ln, hit
    if best:
        return best, best
    title = re.sub(r"[\s_]+", " ", stem).strip()          # as named, so the quote is found
    return title, title


def _codes(s: str) -> list[str]:
    return [c for c in _CODE.findall(s) if any(ch.isdigit() for ch in c) and not c.startswith(("ISO-", "ASTM-"))]


def rules(name: str, path: str, text: str, processes=None) -> dict:  # noqa: PLR0912 - one rule per field
    """A low-confidence proposal from the file name, folder and labels such as "Doc No." and "Rev"."""
    processes = set(processes or _PROCESS_RULES) | {"other"}
    stem = re.sub(r"\.[a-z0-9]{1,5}$", "", name, flags=re.IGNORECASE)
    label = f"{path}/{name}".strip("/")
    head = text[:5000]
    p: dict = {"evidence": {}, "refs": [], "confidence": "low"}

    def put(field, value, quote):
        p[field] = value
        p["evidence"][field] = {"quote": quote}

    m = _TITLE.search(head)
    if m:
        put("title", m.group(1).strip(), _line(head, m.start(1)))
    else:
        put("title", *_title(stem, head))
    m = _LABEL_NO.search(head)
    if m and any(ch.isdigit() for ch in m.group(1)):
        put("number", m.group(1).rstrip(".,;"), _line(head, m.start()))
    else:
        codes = _codes(stem)                                 # codes in the text are usually references
        if codes:
            put("number", codes[0], stem)
    m = _REV.search(head) or _REV.search(stem.replace("_", " "))
    if m:
        src = head if _REV.search(head) else stem.replace("_", " ")
        put("revision", m.group(1).upper(), _line(src, m.start()) if src is head else stem)
    m = _EFFECTIVE.search(head)
    if m and dates_in(m.group(1)):
        put("effective_date", dates_in(m.group(1))[0].isoformat(), _line(head, m.start()))
    m = _OWNER.search(head)
    if m:
        put("owner", m.group(1).strip(), _line(head, m.start()))
    hay = [(norm(label), 3), (norm(p.get("title", "")), 3), (norm(head), 1)]
    for t, rx in _TYPE_RULES:
        if any(re.search(rx, h) for h, _w in hay[:2]):
            put("doc_type", t, _where(rx, label, p["title"], head))
            break
    else:
        put("doc_type", "other", label)
    best, score = "other", 0
    for proc, rx in _PROCESS_RULES.items():
        s = sum(w * len(re.findall(rx, h)) for h, w in hay) if proc in processes else 0
        if s > score:
            best, score = proc, s
    put("process", best, _where(_PROCESS_RULES.get(best), label, p["title"], head))
    words = re.findall(r"[a-z]+", head.lower())
    if len(words) >= 20 and sum(w in {"the", "and", "of", "to", "is", "for", "with"} for w in words) / len(words) > .04:
        p["language"] = "en"
    elif re.search(r"[一-鿿]", head):
        p["language"] = "zh"
    own = p.get("number")
    p["refs"] = sorted({c for c in _codes(text[:50000]) if c != own})[:30]
    return p


def proposal_for_human(p: dict) -> dict:
    """Only the stored fields of a proposal."""
    keys = (*FIELDS, "summary", "refs", "evidence", "confidence")
    return {k: p[k] for k in keys if k in p}
