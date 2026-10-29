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

from wqops import i18n as I18N

TYPES = {"procedure": "Procedure", "work_instruction": "Work instruction", "form": "Form or template",
         "record": "Record", "spec": "Specification or drawing", "certificate": "Certificate",
         "external": "External document", "other": "Other"}
CONTROLLED = {"procedure", "work_instruction", "form"}      # need signed approval to become effective


def type_names() -> dict[str, str]:
    """The document types as the reader sees them: the keys stay, the names are translated."""
    return {k: I18N.label(v) for k, v in TYPES.items()}


FIELDS = ("doc_type", "process", "number", "title", "revision", "effective_date", "owner", "language")
QUOTED = ("doc_type", "process", "number", "title", "revision", "effective_date", "owner")
CORE = ("doc_type", "process", "title")                    # a high-confidence proposal has these verified
LEVELS = ("high", "medium", "low")
MIN_QUOTE = {"doc_type": 8, "process": 8}                  # a type or process needs more than a word to rest on

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


def _size(q: str) -> int:
    """The length of a quote, a Chinese character counting as two letters (来料检验 says as much as "receiving")."""
    return len(q) + len(re.findall(r"[\u3400-\u9fff]", q))


def verify(proposal: dict, name: str, path: str, text: str) -> dict:
    """Check every quote against the file and every value against its quote; set ``verified`` per field and cap the
    confidence: a proposal whose core fields are not all verified is not ``high``."""
    body = corpus(name, path, text)
    ev = {}
    for f in QUOTED:
        if proposal.get(f) in (None, ""):
            continue
        quote = str((proposal.get("evidence") or {}).get(f, {}).get("quote") or "").strip()
        ok = _size(norm(quote)) >= MIN_QUOTE.get(f, 3) and norm(quote) in body
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
_ISO = re.compile(r"(?<![A-Za-z0-9_])(\d{4})-(\d{1,2})-(\d{1,2})(?![A-Za-z0-9_])")   # also next to Chinese text
_US = re.compile(r"(?<![A-Za-z0-9_])(\d{1,2})/(\d{1,2})/(\d{4})(?![A-Za-z0-9_])")
_YMD = re.compile(r"(?<![\d./])(\d{4})([/.])(\d{1,2})\2(\d{1,2})(?![\d./])")             # 2025/9/8, 2025.09.08
_ZH_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")              # 2025年9月8日
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
    for y, _sep, m, d in _YMD.findall(s):
        add(y, m, d)
    for y, m, d in _ZH_DATE.findall(s):
        add(y, m, d)
    return out


# ---------------------------------------------------------------- rules

# Each rule: the English words, then the Chinese ones (23e-3: Chinese companies import their own documents). The
# Chinese words are the usual names in a Chinese quality system (程序文件, 作业指导书, 表单, 记录 ...).
_CJK = r"[\u3400-\u9fff]"
_TYPE_RULES = [
    ("certificate", r"\bcertificate\b|\bcertification\b|\bcert\b|\bcertificate of conformance\b"
                    r"|证书|合格证|证明|质保书|材质单"),
    ("work_instruction", r"\bwork instruction|\bwi[-_ ]\d|\bwi[-_][a-z]"
                         r"|作业指导|操作指导|检验指导书|操作规程|作业规范|作业标准|工艺卡"),
    ("procedure", r"\bprocedure\b|\bsop\b|\bqp[-_ ]\d|\bqp[-_][a-z]"
                  r"|程序|质量手册|质量方针|管理制度"),
    ("form", r"\bform\b|\btemplate\b|\bchecklist\b|(^|/)f[-_][a-z0-9]"
             rf"|表单|表格|模板|报告单|{_CJK}表(?!{_CJK})"),
    ("spec", r"\bspecification\b|\bdrawing\b|\bspec\b|\bdatasheet\b"
             r"|规范|图纸|图样|规格书|规格|技术要求|技术协议"),
    ("record", r"\brecord\b|\blog\b|\bregister\b|\breport\b|\bminutes\b|\bresults\b"
               r"|记录|日志|台账|报告|纪要|结果|清单|名录"),
    ("external", r"\biso \d{4,5}\b|\bastm\b|\bregulation\b|\bstandard\b"
                 r"|外来文件|\bgb(?:/t)? ?\d{4,5}|\byy(?:/t)? ?\d{4,5}|国家标准|行业标准|法规|条例"),
]
_PROCESS_RULES = {
    "document_control": r"document control|control of documents|documents and records"
                        r"|文件控制|文件和记录|文件与记录|记录控制|文件管理|受控文件",
    "training": r"training|competenc|培训|人员能力|能力评价|岗位资格|上岗",
    "purchasing": r"purchas|supplier|vendor|采购|供应商|供方|外包",
    "receiving": r"receiving|incoming inspection|goods receipt|receipt inspection"
                 r"|来料|进货检验|进料检验|到货检验|收货",
    "production": r"production|assembly|manufactur|work order|生产|装配|制造|加工|工单|包装|仓储|仓库|储存|搬运",
    "nonconformance": r"nonconform|non-conform|\bncr\b|不合格|不符合|不良品",
    "capa": r"corrective|preventive|\bcapa\b|纠正|预防措施",
    "calibration": r"calibrat|\bgauges?\b|\bgages?\b|校准|计量|检定|测量设备|监视和测量|量具|检具",
    "complaints": r"complaint|customer feedback|\brma\b|customer return|投诉|客诉|顾客反馈|客户反馈|顾客满意|客户退货",
    "internal_audit": r"internal audit|audit program|audit plan|内审|内部审核|审核方案|审核计划",
    "management_review": r"management review|管理评审|质量方针|质量目标",
}
_LABEL_NO = re.compile(r"(?:doc(?:ument)?\.?\s*(?:no|number|#)|form\s*(?:no|number))\.?\s*[:#]?\s*"
                       r"([A-Za-z0-9][A-Za-z0-9._/-]{1,30})"
                       r"|(?:文件编号|文件编码|文件代号|文件号|表单编号|表格编号|表单号)\s*[:：#]?\s*"
                       r"([A-Za-z0-9][A-Za-z0-9._/-]{1,30})", re.IGNORECASE)
_CODE = re.compile(r"(?<![A-Za-z0-9_])[A-Z]{1,5}(?:-[A-Z0-9]{1,6}){1,3}(?![A-Za-z0-9_])")   # also next to Chinese
_REV_VALUE = r"([A-Z](?:/\d{1,2})?|\d{1,2}(?:\.\d{1,2})?)"
_REV = re.compile(r"(?<![A-Za-z0-9_])rev(?:ision)?\.?\s*[:#]?\s*([A-Z]|\d{1,2}(?:\.\d{1,2})?)(?![A-Za-z0-9_])",
                  re.IGNORECASE)
_REV_ZH = re.compile(rf"(?:版本号?|版次|修订号|修订版)\s*[:：]?\s*{_REV_VALUE}(?![A-Za-z0-9_.])"   # 版本 D, 版本号：B
                     rf"|第\s*{_REV_VALUE}\s*版", re.IGNORECASE)                               # 第 C 版
_EFFECTIVE = re.compile(r"effective(?:\s+date)?\s*:?\s*([^\n|]{6,30})"
                        r"|(?:生效日期|实施日期|生效时间)\s*[:：]?\s*([^\n|]{6,30})", re.IGNORECASE)
_OWNER = re.compile(r"(?:process owner|document owner|owner|prepared by|author)\s*:\s*([^\n|]{2,60})"
                    r"|(?:过程负责人|文件负责人|负责人|编制人|编制|拟制|起草人)\s*[:：]\s*([^\s|:：]{2,30})",
                    re.IGNORECASE)
_TITLE = re.compile(r"(?:^|\n)\s*title\s*:\s*([^\n|]{3,120})"
                    r"|(?:^|\n)\s*(?:文件名称|文件标题|标题)\s*[:：]\s*([^\n|]{2,120})", re.IGNORECASE)


def _g(m: re.Match) -> str:
    """The value a pattern found, whichever of its English or Chinese branches matched."""
    return next(x for x in m.groups() if x is not None)


def _gi(m: re.Match) -> int:
    return next(i for i, x in enumerate(m.groups(), 1) if x is not None)


def _rev(s: str) -> re.Match | None:
    return _REV.search(s) or _REV_ZH.search(s)


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
    name = _REV_ZH.sub(" ", name)
    name = re.sub(r"[\s_]+", " ", name).strip(" -")
    words = set(_words(name)) - _STOP
    best, score = None, (min(2, len(words)), -999)
    for raw in head.splitlines()[:15]:
        ln = raw.strip().lstrip("#").strip()
        if not 4 <= len(ln) <= 120 or "|" in ln or ln.startswith(("Sheet:", "-", "•")) or _LABEL_NO.search(ln) \
                or _rev(ln) or _codes(ln):                       # list items and lines naming other documents
            continue
        lw = _words(ln)
        hit = (len(words & set(lw)), -len(lw))        # most shared words; on a tie the shorter line
        if hit[0] >= score[0] and hit > score:
            best, score = ln, hit
    if best:
        return best, best
    title = re.sub(r"[\s_]+", " ", stem).strip()          # as named, so the quote is found
    return title, title


def _words(s: str) -> list[str]:
    """The words of a line for comparing it with the file name: English words of three letters or more, and the
    pairs of neighbouring Chinese characters (Chinese has no spaces: 来料检验 -> 来料, 料检, 检验)."""
    out = re.findall(r"[a-z]{3,}", s.lower())
    for run in re.findall(rf"{_CJK}{{2,}}", s):
        out += [run[i:i + 2] for i in range(len(run) - 1)]
    return out


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
        put("title", _g(m).strip(), _line(head, m.start(_gi(m))))
    else:
        put("title", *_title(stem, head))
    m = _LABEL_NO.search(head)
    if m and any(ch.isdigit() for ch in _g(m)):
        put("number", _g(m).rstrip(".,;"), _line(head, m.start()))
    else:
        codes = _codes(stem)                                 # codes in the text are usually references
        if codes:
            put("number", codes[0], stem)
    m = _rev(head) or _rev(stem.replace("_", " "))
    if m:
        src = head if _rev(head) else stem.replace("_", " ")
        put("revision", _g(m).upper(), _line(src, m.start()) if src is head else stem)
    m = _EFFECTIVE.search(head)
    if m and dates_in(_g(m)):
        put("effective_date", dates_in(_g(m))[0].isoformat(), _line(head, m.start()))
    m = _OWNER.search(head)
    if m:
        put("owner", _g(m).strip(), _line(head, m.start()))
    hay = [(norm(label), 3), (norm(p.get("title", "")), 3), (norm(head), 1)]
    # Chinese folder trees are named by document level ("程序文件", "四级文件 表单记录") and hold several types:
    # there the file's own name and title decide before its folder.
    looks = [[norm(name), hay[1][0]], [hay[0][0]]] if re.search(_CJK, path) else [[h for h, _w in hay[:2]]]
    found = next(((t, rx) for where in looks for t, rx in _TYPE_RULES if any(re.search(rx, h) for h in where)), None)
    if found:
        put("doc_type", found[0], _where(found[1], label, p["title"], head))
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
