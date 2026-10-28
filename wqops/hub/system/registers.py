"""Quality registers (ADR-0016, step 16b): simple records whose fields come from the process pack, so a company's
registers can change without code. Entries of a signed register are approved with a password and then locked; any
entry can be voided with a reason; nothing is deleted and every change is logged.

Plain code: no AI, no network (tests/test_isolation.py).
"""

from __future__ import annotations

import datetime as dt
import math

from psycopg.types.json import Jsonb

from wqops import i18n as I18N
from wqops.hub.quality import records as Q
from wqops.hub.system import qms as QMS
from wqops.hub.system import rules as R
from wqops.i18n import say

TYPES = R.REGISTER_TYPES
YES = {"yes", "y", "true", "1", "done", "closed", "x"}
NO = {"no", "n", "false", "0", "open", "not done"}


class RegisterError(ValueError):
    pass


def specs() -> dict[str, dict]:
    """The quality registers, shared by every standard's pack (packs/registers.yaml)."""
    return QMS.shared_registers() or {}


def spec(name: str) -> dict:
    s = specs().get(name)
    if s is None:
        raise KeyError(name)
    return s


def shown(s: dict) -> dict:
    """A register's definition in the reader's language: its name, field names and signature text, on the way out
    (ADR-0023). The choices stay as they are: they are the values people pick and that are saved."""
    return I18N.localize(s, I18N.LABEL_KEYS | {"sign"})


def _sep() -> str:
    return "、" if I18N.current() == "zh" else ", "


def check_specs(regs: dict) -> list[str]:
    return R.check_registers(regs)


def _date(v) -> str:
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    return dt.date.fromisoformat(str(v).strip()[:10]).isoformat()


def clean(s: dict, values: dict, *, partial: bool = False) -> dict:  # noqa: PLR0912 - one branch per field type
    """Values checked against the register's fields; an empty value leaves the field out (unknown)."""
    if not isinstance(values, dict):
        raise RegisterError(say("values are given by field"))
    fields = s["fields"]
    out = {}
    for f, raw in values.items():
        if f not in fields:
            raise RegisterError(say("{label} has no field {f}", label=I18N.label(s['label']), f=repr(f)))
        x = fields[f]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            if x["type"] == "number":
                v = float(str(raw).replace(",", ""))
                if math.isnan(v) or math.isinf(v):
                    raise ValueError
                out[f] = int(v) if v.is_integer() else v
            elif x["type"] == "date":
                out[f] = _date(raw)
            elif x["type"] == "yesno":
                w = str(raw).strip().lower()
                if raw is True or w in YES:
                    out[f] = True
                elif raw is False or w in NO:
                    out[f] = False
                else:
                    raise ValueError
            elif x["type"] == "choice":
                w = str(raw).strip().lower()
                hit = next((c for c in x["choices"] if c.lower() == w), None)
                if hit is None:
                    raise ValueError
                out[f] = hit
            else:
                out[f] = str(raw).strip()[:4000 if x["type"] == "longtext" else 300]
        except (ValueError, TypeError) as exc:
            t = x["type"]
            kind = say("a number") if t == "number" else say("a date like 2026-10-31") if t == "date" else \
                say("yes or no") if t == "yesno" else \
                say("one of {list}", list=", ".join(x.get("choices") or [])) if t == "choice" else say("kind::text")
            raise RegisterError(say("{label}: {kind}", label=I18N.label(x['label']), kind=kind)) from exc
    if not partial:
        missing = [I18N.label(x["label"]) for f, x in fields.items() if x.get("required") and f not in out]
        if missing:
            raise RegisterError(say("still needed: {list}", list=_sep().join(missing)))
    return out


def log(conn, entry_id: int, email: str, action: str, note: str = "") -> None:
    conn.execute("insert into qms_register_log (entry_id, email, action, note) values (%s, %s, %s, %s)",
                 (entry_id, email, action, note[:2000]))


def get(conn, entry_id: int) -> dict:
    row = conn.execute("select * from qms_register_entries where id = %s", (entry_id,)).fetchone()
    if row is None:
        raise KeyError(entry_id)
    return row


def create(conn, email: str, name: str, values: dict, *, source_doc: int | None = None,
           source_row: int | None = None, note: str = "") -> dict:
    """A new entry. One brought in by a signed ledger import (source_doc) of a signed register is approved by that
    import and locked like any approved entry."""
    s = spec(name)
    vals = clean(s, values)
    approved = bool(source_doc and s.get("sign"))
    with conn.transaction():
        row = conn.execute("insert into qms_register_entries (register, \"values\", created_by, source_doc, "
                           "source_row, status, signed_by, signed_at) values (%s, %s, %s, %s, %s, %s, %s, "
                           "case when %s then now() end) returning *",
                           (name, Jsonb(vals), email, source_doc, source_row, "signed" if approved else "open",
                            email if approved else None, approved)).fetchone()
        log(conn, row["id"], email, "recorded", note)
        if approved:
            log(conn, row["id"], email, "approved", say("by the signed import of the old records"))
    return row


def update(conn, email: str, entry_id: int, values: dict) -> dict:
    with conn.transaction():
        row = conn.execute("select * from qms_register_entries where id = %s for update", (entry_id,)).fetchone()
        if row is None:
            raise KeyError(entry_id)
        if row["status"] != "open":
            raise RegisterError(say("this entry is approved; void it with a reason and record a new one")
                                if row["status"] == "signed" else
                                say("this entry is void; void it with a reason and record a new one"))
        s = spec(row["register"])
        merged = clean(s, {**row["values"], **values})
        changed = [I18N.label(s["fields"][f]["label"]) for f in s["fields"] if merged.get(f) != row["values"].get(f)]
        if not changed:
            return row
        out = conn.execute("update qms_register_entries set \"values\" = %s, updated_at = now() where id = %s "
                           "returning *", (Jsonb(merged), entry_id)).fetchone()
        log(conn, entry_id, email, "changed", _sep().join(changed))
    return out


def sign(conn, user: dict, entry_id: int, password: str) -> dict:
    row = get(conn, entry_id)
    s = spec(row["register"])
    if not s.get("sign"):
        raise RegisterError(say("{label} entries are not approved with a signature", label=I18N.label(s['label'])))
    if row["status"] != "open":
        raise RegisterError(say("this entry is already approved") if row["status"] == "signed"
                            else say("this entry is already void"))
    Q.check_signer(conn, user, password)
    with conn.transaction():
        out = conn.execute("update qms_register_entries set status = 'signed', signed_by = %s, signed_at = now() "
                           "where id = %s and status = 'open' returning *", (user["email"], entry_id)).fetchone()
        if out is None:
            raise RegisterError(say("this entry changed meanwhile; look at it again"))
        Q._sign(conn, user, I18N.label(s["sign"]), "register", entry_id, f"{I18N.label(s['label'])} #{entry_id}")
        log(conn, entry_id, user["email"], "approved", I18N.label(s["sign"]))
    return out


def void(conn, user: dict, entry_id: int, reason: str, password: str = "") -> dict:
    """Void an entry with a reason; an approved one also needs the person's password."""
    email = user["email"]
    if not reason.strip():
        raise RegisterError(say("say why the entry is void"))
    if get(conn, entry_id)["status"] == "signed":
        Q.check_signer(conn, user, password)
    with conn.transaction():
        row = conn.execute("select * from qms_register_entries where id = %s for update", (entry_id,)).fetchone()
        if row is None:
            raise KeyError(entry_id)
        if row["status"] == "void":
            raise RegisterError(say("this entry is already void"))
        out = conn.execute("update qms_register_entries set status = 'void', void_reason = %s, updated_at = now() "
                           "where id = %s returning *", (reason.strip()[:1000], entry_id)).fetchone()
        log(conn, entry_id, email, "void", reason.strip())
    return out


def history(conn, entry_id: int) -> list[dict]:
    rows = conn.execute("select at, email, action, note from qms_register_log where entry_id = %s order by id",
                        (entry_id,)).fetchall()
    return [dict(r, at=r["at"].isoformat()) for r in rows]


def entries(conn, name: str, *, with_void: bool = True) -> list[dict]:
    spec(name)
    rows = conn.execute("select * from qms_register_entries where register = %s order by id desc", (name,)).fetchall()
    return [r for r in rows if with_void or r["status"] != "void"]


def counts(conn) -> dict[str, dict]:
    out = {}
    for r in conn.execute("select register, status, count(*) as n from qms_register_entries group by 1, 2"):
        out.setdefault(r["register"], {})[r["status"]] = r["n"]
    return out


