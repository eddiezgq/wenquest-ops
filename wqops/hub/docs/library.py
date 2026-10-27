"""The document library (ADR-0014 items 1, 5-7): import batches, review and confirmation, controlled documents,
search and the overview.

Controlled documents (procedures, work instructions, forms): draft -> in_review -> effective -> obsolete. Approval is
signed with the approver's password by someone other than the person who uploaded, confirmed or submitted it; the
file's fingerprint is frozen at approval and a new revision makes the old one obsolete. Records, certificates and
external documents are kept on confirmation (``confirmed``, fingerprint frozen) without approval. Obsolete needs a
reason. ``doc_log`` and ``signatures`` are append-only in the database and documents cannot be deleted.

Plain code: no AI, no network (tests/test_isolation.py). Permission checks by role are the API's job; separation of
duties is checked here.
"""

from __future__ import annotations

import datetime as dt
import re

from psycopg.types.json import Jsonb

from wqops.hub.docs import checks as CK
from wqops.hub.docs import classify as K
from wqops.hub.docs import control as CTL
from wqops.hub.docs import extract as X
from wqops.hub.docs import store as F
from wqops.hub.quality import records as Q
from wqops.i18n import say

KEPT = ("draft", "in_review", "approved", "effective", "confirmed")      # in the library
CHARS_PER_TOKEN = 4
TOKENS_PER_FILE = 1500                                      # instructions and the reply, per file


class DocError(ValueError):
    pass


def log(conn, doc_id: int, email: str | None, action: str, note: str = "") -> None:
    conn.execute("insert into doc_log (document_id, email, action, note) values (%s, %s, %s, %s)",
                 (doc_id, email, action, (note or "")[:2000]))


def history(conn, doc_id: int) -> list[dict]:
    rows = conn.execute("select at, email, action, note from doc_log where document_id = %s order by id",
                        (doc_id,)).fetchall()
    return [dict(r, at=r["at"].isoformat()) for r in rows]


def get(conn, doc_id: int) -> dict:
    row = conn.execute("select * from documents where id = %s", (doc_id,)).fetchone()
    if row is None:
        raise KeyError(doc_id)
    return row


def processes(conn) -> dict[str, str]:
    return {r["code"]: r["name"] for r in conn.execute("select code, name from doc_processes order by sort, code")}


# ---------------------------------------------------------------- import

def clean_path(raw: str) -> tuple[str, str]:
    """(folder path, file name) from a browser's relative path or a zip entry; never leaves the import."""
    parts = [p for p in re.split(r"[\\/]+", raw or "") if p not in ("", ".", "..")]
    if not parts:
        raise DocError(say("a file needs a name"))
    return "/".join(parts[:-1])[:500], parts[-1][:255]


def new_import(conn, email: str, label: str = "") -> dict:
    return conn.execute("insert into doc_imports (created_by, label) values (%s, %s) returning *",
                        (email, label.strip()[:200])).fetchone()


def get_import(conn, import_id: int) -> dict:
    row = conn.execute("select * from doc_imports where id = %s", (import_id,)).fetchone()
    if row is None:
        raise KeyError(import_id)
    return row


def add_file(conn, import_id: int, raw_name: str, data: bytes) -> dict:
    """Store one file of an import; identical bytes are stored once and the row points to the first copy."""
    path, name = clean_path(raw_name)
    if not X.accepted(name):
        raise DocError(say("{name}: this kind of file is not taken (PDF, Word, Excel, CSV, text and images are)",
                           name=name))
    if len(data) > F.MAX_BYTES:
        raise DocError(say("{name}: larger than {v} MB", name=name, v=F.MAX_BYTES // (1024 * 1024)))
    if not data:
        raise DocError(say("{name}: the file is empty", name=name))
    sha = F.put(data)
    first = conn.execute("select id from documents where sha256 = %s and status <> 'rejected' order by id limit 1",
                         (sha,)).fetchone()
    row = conn.execute(
        "insert into documents (import_id, sha256, size_bytes, original_name, path, mime, duplicate_of) "
        "values (%s, %s, %s, %s, %s, %s, %s) returning *",
        (import_id, sha, len(data), name, path, X.mime(name), first["id"] if first else None)).fetchone()
    conn.execute("update doc_imports set files = files + 1 where id = %s", (import_id,))
    return row


def skip(conn, import_id: int, name: str, reason: str) -> None:
    conn.execute("update doc_imports set skipped = skipped || %s where id = %s",
                 (Jsonb([{"name": name, "reason": reason}]), import_id))


def _set_text(conn, doc: dict, t: X.Text) -> None:
    conn.execute("insert into doc_text (document_id, body) values (%s, %s) on conflict (document_id) do update "
                 "set body = excluded.body", (doc["id"], t.body))
    conn.execute("update documents set text_status = %s, text_chars = %s, updated_at = now() where id = %s",
                 (t.status, len(t.body), doc["id"]))
    log(conn, doc["id"], None, "text", f"{t.status}, {len(t.body)} characters" + (f"; {t.note}" if t.note else ""))


def extract_one(conn, doc: dict) -> None:
    same = conn.execute("select d.text_status, t.body from documents d join doc_text t on t.document_id = d.id "
                        "where d.sha256 = %s and d.id <> %s and d.text_status <> 'pending' limit 1",
                        (doc["sha256"], doc["id"])).fetchone()
    if same:
        _set_text(conn, doc, X.Text(same["body"], same["text_status"], "same file as an earlier one"))
    else:
        try:
            data = F.get(doc["sha256"])
        except OSError as exc:                          # missing or damaged in the store: say so, go on
            _set_text(conn, doc, X.Text("", "error", f"stored file unreadable: {exc}"))
            return
        _set_text(conn, doc, X.text_of(doc["original_name"], data))


def extract_import(conn, import_id: int) -> dict:
    """Take the text of every file of the import, then mark it ready for classification."""
    for doc in conn.execute("select * from documents where import_id = %s and text_status = 'pending' order by id",
                            (import_id,)).fetchall():
        extract_one(conn, doc)
    return conn.execute("update doc_imports set status = 'ready' where id = %s returning *", (import_id,)).fetchone()


def recover(conn) -> list[int]:
    """After a restart: work that stopped half-way. Classification is marked as stopped (classify again); imports
    whose text was being read are returned so the reading can continue."""
    conn.execute("update doc_imports set status = 'done', error = 'classification stopped when the hub restarted; "
                 "classify again' where status = 'classifying'")
    return [r["id"] for r in conn.execute("select id from doc_imports where status = 'extracting' order by id")]


def text(conn, doc_id: int) -> str:
    r = conn.execute("select body from doc_text where document_id = %s", (doc_id,)).fetchone()
    return r["body"] if r else ""


def estimate(conn, import_id: int) -> dict:
    """What classifying this import with the model would read: files, characters and roughly how many tokens."""
    r = conn.execute("select count(*) as files, coalesce(sum(least(text_chars, %s)), 0) as chars from documents "
                     "where import_id = %s and status = 'to_classify' and duplicate_of is null",
                     (EXCERPT_CHARS, import_id)).fetchone()
    return {"files": r["files"], "chars": int(r["chars"]),
            "tokens": int(r["chars"]) // CHARS_PER_TOKEN + r["files"] * TOKENS_PER_FILE}


EXCERPT_CHARS = 16000


def excerpt(body: str, limit: int = EXCERPT_CHARS) -> str:
    """The whole text of a short file; for a long one its start, its section headings and its end."""
    if len(body) <= limit:
        return body
    head, tail = body[: limit * 5 // 8], body[-limit // 8:]
    heads = [ln.strip() for ln in body[len(head):-len(tail)].splitlines()
             if 3 <= len(ln.strip()) <= 90 and re.match(r"^(\d+(\.\d+)*\.?\s+\S|[A-Z][A-Z0-9 ,&/-]{3,}$)", ln.strip())]
    middle = "\n".join(heads)[: limit // 4]
    return (f"{head}\n\n[... section headings from the middle of the file ...]\n{middle}\n\n"
            f"[... end of the file ...]\n{tail}")


# ---------------------------------------------------------------- proposals and review

def propose(conn, doc_id: int, proposal: dict, engine: str, ai_run: int | None = None) -> dict:
    """Store a classification proposal (from the model or the rules) for a person to review."""
    p = K.proposal_for_human(proposal)
    eff = p.get("effective_date")
    row = conn.execute(
        "update documents set status = 'to_review', engine = %s, confidence = %s, doc_type = %s, process = %s, "
        "number = %s, title = %s, revision = %s, effective_date = %s, owner = %s, language = %s, summary = %s, "
        "refs = %s, evidence = %s, ai_run = %s, updated_at = now() where id = %s and status in ('to_classify', "
        "'to_review') returning *",
        (engine, p.get("confidence", "low"), p.get("doc_type"), p.get("process"), p.get("number"), p.get("title"),
         p.get("revision"), eff, p.get("owner"), p.get("language"), p.get("summary"), Jsonb(p.get("refs", [])),
         Jsonb(p.get("evidence", {})), ai_run, doc_id)).fetchone()
    if row is None:
        raise DocError(say("document {doc_id} is not waiting for classification", doc_id=doc_id))
    log(conn, doc_id, None, "classified", f"{engine}, confidence {p.get('confidence', 'low')}")
    return row


def _check_fields(conn, f: dict) -> None:
    if f.get("doc_type") not in K.TYPES:
        raise DocError(say("choose a type"))
    if f.get("process") not in processes(conn):
        raise DocError(say("choose a process"))
    if not str(f.get("title") or "").strip():
        raise DocError(say("a document needs a title"))
    if f.get("effective_date"):
        try:
            dt.date.fromisoformat(str(f["effective_date"]))
        except ValueError as exc:
            raise DocError(say("effective date must be a date (YYYY-MM-DD)")) from exc


EDITABLE = ("doc_type", "process", "number", "title", "revision", "effective_date", "owner", "language", "summary")


def confirm(conn, email: str, doc_id: int, changes: dict | None = None) -> dict:
    """A person confirms the classification, changing any field first. Changed fields are kept as hints for later
    classification. Controlled types become drafts; the others are kept at once with their fingerprint frozen."""
    with conn.transaction():
        doc = conn.execute("select * from documents where id = %s for update", (doc_id,)).fetchone()
        if doc is None:
            raise KeyError(doc_id)
        if doc["status"] not in ("to_review", "to_classify"):
            raise DocError(say("document {doc_id} is {status}; nothing to confirm",
                               doc_id=doc_id, status=doc['status'].replace('_', ' ')))
        changes = {k: (str(v).strip() or None) if v is not None else None for k, v in (changes or {}).items()
                   if k in EDITABLE}
        f = {k: doc[k] for k in EDITABLE} | changes
        if isinstance(f.get("effective_date"), dt.date):
            f["effective_date"] = f["effective_date"].isoformat()
        _check_fields(conn, f)
        corrected = [{"field": k, "from": str(doc[k]) if doc[k] is not None else None, "to": v}
                     for k, v in changes.items() if (str(doc[k]) if doc[k] is not None else None) != v]
        # a document the model drafted (ADR-0016, 16c) is approved by someone else whatever its type
        kept = f["doc_type"] not in K.CONTROLLED and not doc.get("ai_drafted") and not doc.get("generated_from")
        row = conn.execute(
            "update documents set doc_type = %s, process = %s, number = %s, title = %s, revision = %s, "
            "effective_date = %s, owner = %s, language = %s, summary = %s, corrected = %s, confirmed_by = %s, "
            "confirmed_at = now(), status = %s, fingerprint = %s, engine = coalesce(engine, 'person'), "
            "updated_at = now() where id = %s returning *",
            (*(f[k] for k in EDITABLE), Jsonb(corrected), email, "confirmed" if kept else "draft",
             doc["sha256"] if kept else None, doc_id)).fetchone()
        note = "; ".join(f"{c['field']}: {c['from'] or '-'} -> {c['to'] or '-'}" for c in corrected)
        log(conn, doc_id, email, "confirmed", (note or "as proposed") + ("; kept in the library" if kept else
                                                                          "; draft, needs approval"))
    return row


def confirm_batch(conn, email: str, ids: list[int]) -> dict:
    """Confirm several high-confidence, fully verified proposals as they are; the rest are left for one by one."""
    done, left = [], []
    for i in ids:
        doc = conn.execute("select * from documents where id = %s", (i,)).fetchone()
        if doc and doc["status"] == "to_review" and K.batch_ok(doc):
            confirm(conn, email, i)
            done.append(i)
        else:
            left.append(i)
    return {"confirmed": done, "left": left}


def reject(conn, email: str, doc_id: int, reason: str) -> dict:
    """Not a document to keep (a stray file, a draft copy). The file stays in the import record."""
    if not reason.strip():
        raise DocError(say("say why this file is not kept"))
    row = conn.execute("update documents set status = 'rejected', updated_at = now() where id = %s and status in "
                       "('to_classify', 'to_review') returning *", (doc_id,)).fetchone()
    if row is None:
        get(conn, doc_id)
        raise DocError(say("document {doc_id} is already in the library; make it obsolete instead", doc_id=doc_id))
    log(conn, doc_id, email, "not kept", reason.strip())
    return row


def hints(conn, limit: int = 30) -> list[dict]:
    """What people corrected in earlier proposals, newest first: given to the model as this company's practice."""
    rows = conn.execute("select original_name, path, corrected from documents where corrected <> '[]' "
                        "order by confirmed_at desc nulls last limit %s", (limit,)).fetchall()
    return [{"file": f"{r['path']}/{r['original_name']}".strip("/"), "changes": r["corrected"]} for r in rows]


# ---------------------------------------------------------------- controlled documents

def _lock(conn, doc_id: int) -> dict:
    doc = conn.execute("select * from documents where id = %s for update", (doc_id,)).fetchone()
    if doc is None:
        raise KeyError(doc_id)
    return doc


def _uploader(conn, doc: dict) -> str | None:
    r = conn.execute("select created_by from doc_imports where id = %s", (doc["import_id"],)).fetchone()
    return r["created_by"] if r else None


def name_of(doc: dict) -> str:
    return " ".join(x for x in (doc["number"], doc["title"], f"rev {doc['revision']}" if doc["revision"] else None)
                    if x) or doc["original_name"]


def _no_clash(conn, doc: dict) -> None:
    """One revision of a number at a time: not the same revision twice, and no second effective revision unless this
    one was uploaded as the new revision of it."""
    same = conn.execute("select id from documents where number = %s and revision = %s and id <> %s and status in "
                        "('in_review', 'approved', 'effective', 'obsolete')",
                        (doc["number"], doc["revision"], doc["id"])).fetchone()
    if same:
        raise DocError(say("{number} rev {revision} already exists (document {id})",
                           number=doc['number'], revision=doc['revision'], id=same['id']))
    other = conn.execute("select id, revision, status from documents where number = %s and status in ('approved', "
                         "'effective') and id <> %s and id is distinct from %s and supersedes is distinct from %s",
                         (doc["number"], doc["id"], doc["supersedes"], doc["id"])).fetchone()
    if other:
        raise DocError(say("{number} rev {revision} is {status} (document {id}): upload this as a new revision of "
                           "it, or make that one obsolete first",
                           number=doc['number'], revision=other['revision'], status=other['status'], id=other['id']))


def involved(conn, doc: dict) -> set[str]:
    """Everyone who uploaded, confirmed or ever sent this document for approval: none of them may approve it."""
    sent = {r["email"] for r in conn.execute("select email from doc_log where document_id = %s and action = "
                                            "'sent for approval'", (doc["id"],)) if r["email"]}
    return (sent | {doc["submitted_by"], doc["confirmed_by"], _uploader(conn, doc)}) - {None}


def edit(conn, email: str, doc_id: int, changes: dict) -> dict:
    """Correct the details of a draft (for example add the number before sending it for approval)."""
    with conn.transaction():
        doc = _lock(conn, doc_id)
        if doc["status"] != "draft":
            raise DocError(say("only a draft can be changed; an effective document changes by a new revision"))
        changes = {k: (str(v).strip() or None) if v is not None else None for k, v in (changes or {}).items()
                   if k in EDITABLE}
        f = {k: doc[k] for k in EDITABLE} | changes
        if isinstance(f.get("effective_date"), dt.date):
            f["effective_date"] = f["effective_date"].isoformat()
        _check_fields(conn, f)
        if f["doc_type"] not in K.CONTROLLED and not (doc.get("ai_drafted") or doc.get("generated_from")):
            raise DocError(say("a draft stays a procedure, work instruction or form; to keep it as a record, make it "
                               "obsolete after approval or ask for it to be imported again"))
        before = {k: (str(doc[k]) if doc[k] is not None else None) for k in EDITABLE}
        diff = {k: v for k, v in changes.items() if before[k] != v}
        if not diff:
            return doc
        row = conn.execute("update documents set " + ", ".join(f"{k} = %({k})s" for k in diff)  # noqa: S608 - fixed names
                           + ", updated_at = now() where id = %(id)s returning *", diff | {"id": doc_id}).fetchone()
        log(conn, doc_id, email, "changed",
            "; ".join(f"{k}: {before[k] or '-'} -> {v or '-'}" for k, v in diff.items()))
    return row


def submit(conn, email: str, doc_id: int) -> dict:
    with conn.transaction():
        doc = _lock(conn, doc_id)
        if doc["status"] != "draft":
            raise DocError(say("only a draft can be sent for approval; this one is {status}",
                               status=doc['status'].replace('_', ' ')))
        if not doc["number"] or not doc["revision"]:
            raise DocError(say("give the document a number and a revision before sending it for approval"))
        _no_clash(conn, doc)
        row = conn.execute("update documents set status = 'in_review', submitted_by = %s, updated_at = now() "
                           "where id = %s returning *", (email, doc_id)).fetchone()
        log(conn, doc_id, email, "sent for approval")
    return row


def send_back(conn, email: str, doc_id: int, reason: str) -> dict:
    if not reason.strip():
        raise DocError(say("say what needs to change"))
    with conn.transaction():
        doc = _lock(conn, doc_id)
        if doc["status"] != "in_review":
            raise DocError(say("only a document waiting for approval can be sent back"))
        row = conn.execute("update documents set status = 'draft', updated_at = now() where id = %s returning *",
                           (doc_id,)).fetchone()
        log(conn, doc_id, email, "sent back", reason.strip())
    return row


def approve(conn, user: dict, doc_id: int, password: str, today: dt.date,  # noqa: PLR0917
            effective_on: dt.date | None = None) -> dict:
    """Signed approval by someone other than the uploader, the confirmer and the submitter. The fingerprint is frozen.
    It takes effect today, or on a later day the approver sets (to leave time for reading it); then an earlier
    revision it replaces becomes obsolete and the people who must read it are asked to."""
    def allowed(doc):
        if doc["status"] != "in_review":
            raise DocError(say("only a document waiting for approval can be approved"))
        if user["email"] in involved(conn, doc):
            raise PermissionError(say("approval must come from someone who did not upload, confirm or submit it"))

    if effective_on is not None and effective_on < today:
        raise DocError(say("it cannot take effect before the day it is approved"))
    first = get(conn, doc_id)
    allowed(first)
    if effective_on is None and first["effective_date"] and first["effective_date"] > today:
        effective_on = first["effective_date"]          # a later day written on the draft is a planned day
    Q.check_signer(conn, user, password)              # outside the transaction: a failed attempt stays recorded
    with conn.transaction():
        doc = _lock(conn, doc_id)
        allowed(doc)
        _no_clash(conn, doc)
        Q._sign(conn, user, "Document approved", "document", doc_id, name_of(doc))
        later = effective_on is not None and effective_on > today
        row = conn.execute(
            "update documents set status = %s, approved_by = %s, approved_at = now(), fingerprint = sha256, "
            "effective_date = %s, updated_at = now() where id = %s returning *",
            ("approved" if later else "effective", user["email"],
             effective_on if later else (doc["effective_date"] or today), doc_id)).fetchone()
        if later:
            log(conn, doc_id, user["email"], "approved", f"takes effect on {effective_on}; fingerprint "
                                                           f"{doc['sha256'][:12]}")
        else:
            log(conn, doc_id, user["email"], "approved, effective", f"fingerprint {doc['sha256'][:12]}")
            _took_effect(conn, row, user["email"], today)
    return row


def _took_effect(conn, doc: dict, email: str, today: dt.date) -> None:
    if doc["supersedes"]:
        old = conn.execute("update documents set status = 'obsolete', obsolete_reason = %s, updated_at = now() "
                           "where id = %s and status = 'effective' returning id",
                           (f"replaced by revision {doc['revision']}", doc["supersedes"])).fetchone()
        if old:
            log(conn, old["id"], email, "obsolete", f"replaced by revision {doc['revision']} (document {doc['id']})")
    CTL.on_effective(conn, doc, email, today)


def take_effect_due(conn, today: dt.date) -> list[int]:
    """Approved revisions whose day has come take effect (the daily job; also when the library is opened)."""
    done = []
    for d in conn.execute("select id from documents where status = 'approved' and effective_date <= %s order by id",
                          (today,)).fetchall():
        with conn.transaction():
            doc = conn.execute("select * from documents where id = %s and status = 'approved' for update",
                               (d["id"],)).fetchone()
            if doc is None:
                continue
            try:
                _no_clash(conn, doc)
            except DocError as exc:          # another revision took effect meanwhile: a person sorts it out
                log(conn, doc["id"], "WenQuest Ops", "not made effective", str(exc))
                continue
            row = conn.execute("update documents set status = 'effective', updated_at = now() where id = %s "
                               "returning *", (doc["id"],)).fetchone()
            log(conn, doc["id"], "WenQuest Ops", "effective", f"planned for {doc['effective_date']}")
            _took_effect(conn, row, "WenQuest Ops", today)
            done.append(doc["id"])
    return done


def obsolete(conn, email: str, doc_id: int, reason: str) -> dict:
    if not reason.strip():
        raise DocError(say("say why the document is obsolete"))
    with conn.transaction():
        doc = _lock(conn, doc_id)
        if doc["status"] not in ("effective", "confirmed", "approved"):
            raise DocError(say("only an effective, approved or kept document can be made obsolete"))
        row = conn.execute("update documents set status = 'obsolete', obsolete_reason = %s, updated_at = now() "
                           "where id = %s returning *", (reason.strip(), doc_id)).fetchone()
        log(conn, doc_id, email, "obsolete" if doc["status"] != "approved" else "withdrawn before taking effect",
            reason.strip())
        conn.execute("update doc_training set status = 'superseded', done_at = now(), note = %s where document_id = "
                     "%s and status = 'pending'", (f"document made obsolete: {reason.strip()}"[:1000], doc_id))
    return row


def new_revision(conn, email: str, doc_id: int, *, name: str, data: bytes, revision: str) -> dict:
    """Upload the next revision of an effective document; it starts as a draft and replaces the old one when
    approved. The old file is never replaced."""
    revision = (revision or "").strip()
    with conn.transaction():
        old = _lock(conn, doc_id)
        if old["status"] != "effective" or old["doc_type"] not in K.CONTROLLED:
            raise DocError(say("a new revision starts from an effective procedure, work instruction or form"))
        if not revision or revision == old["revision"]:
            raise DocError(say("give the new revision a name different from the current one"))
        if conn.execute("select 1 from documents where supersedes = %s and status in ('draft', 'in_review', "
                        "'approved')",
                        (doc_id,)).fetchone():
            raise DocError(say("a new revision of this document is already in progress"))
        imp = new_import(conn, email, f"New revision of {old['number'] or old['title']}")
        doc = add_file(conn, imp["id"], name, data)
        if doc["sha256"] == old["sha256"]:
            raise DocError(say("this is the same file as the current revision"))
        conn.execute("update doc_imports set status = 'done', engine = 'person' where id = %s", (imp["id"],))
        extract_one(conn, doc)
        row = conn.execute(
            "update documents set status = 'draft', engine = 'person', confidence = null, doc_type = %s, "
            "process = %s, number = %s, title = %s, revision = %s, owner = %s, language = %s, summary = %s, "
            "supersedes = %s, confirmed_by = %s, confirmed_at = now(), duplicate_of = null, trainees = %s, "
            "updated_at = now() where id = %s returning *",
            (old["doc_type"], old["process"], old["number"], old["title"], revision, old["owner"], old["language"],
             old["summary"], doc_id, email, Jsonb(old["trainees"]), doc["id"])).fetchone()
        log(conn, row["id"], email, "new revision", f"revision {revision} of document {doc_id}")
        log(conn, doc_id, email, "new revision started", f"revision {revision} (document {row['id']})")
    return row


# ---------------------------------------------------------------- reading

LIST_COLS = ("id, import_id, original_name, path, size_bytes, mime, duplicate_of, text_status, text_chars, status, "
             "engine, confidence, doc_type, process, number, title, revision, effective_date, owner, language, "
             "summary, refs, evidence, supersedes, approved_by, updated_at")


def listing(conn, *, status: str = "library", process: str = "", doc_type: str = "", q: str = "",
            import_id: int | None = None, limit: int = 500) -> list[dict]:
    where, args = [], {}
    if status == "library":
        where.append("d.status = any(%(kept)s)")
        args["kept"] = list(KEPT)
    elif status != "all":
        where.append("d.status = %(status)s")
        args["status"] = status
    for k, v in (("process", process), ("doc_type", doc_type)):
        if v:
            where.append(f"d.{k} = %({k})s")
            args[k] = v
    if import_id is not None:
        where.append("d.import_id = %(imp)s")
        args["imp"] = import_id
    rank, snippet = "", "null"
    words = re.findall(r"\w+", q.lower())[:12]
    if words:
        args["q"] = " & ".join(f"{w}:*" for w in words)          # every word, as a prefix ("nonconform")
        args["like"] = "%" + q.strip().replace("%", r"\%").replace("_", r"\_") + "%"
        where.append("(t.tsv @@ to_tsquery('simple', %(q)s) or d.title ilike %(like)s or d.number ilike %(like)s "
                     "or d.original_name ilike %(like)s)")
        rank = "ts_rank(t.tsv, to_tsquery('simple', %(q)s))"
        snippet = ("ts_headline('simple', left(t.body, 200000), to_tsquery('simple', %(q)s), "
                   "'MaxFragments=2, MaxWords=18, MinWords=6, StartSel=<<, StopSel=>>')")
    cols = ", ".join(f"d.{c.strip()}" for c in LIST_COLS.split(","))
    sql = (f"select {cols}, {snippet} as snippet from documents d left join doc_text t on t.document_id = d.id"  # noqa: S608
           + (" where " + " and ".join(where) if where else "")
           + f" order by {rank + ' desc, ' if rank else ''}d.process nulls last, d.number nulls last, d.id "
           "limit %(limit)s")
    args["limit"] = max(1, min(limit, 2000))
    return conn.execute(sql, args).fetchall()


def overview(conn) -> dict:
    """Documents in the library by process and type, plus what waits for review (ADR-0014 item 7)."""
    rows = conn.execute("select process, doc_type, status, count(*) as n from documents where status <> 'rejected' "
                        "group by 1, 2, 3").fetchall()
    grid: dict[str, dict[str, int]] = {}
    totals = {"library": 0, "to_review": 0, "to_classify": 0, "in_review": 0, "approved": 0, "draft": 0,
              "obsolete": 0}
    for r in rows:
        if r["status"] in KEPT:
            cell = grid.setdefault(r["process"] or "other", {})
            cell[r["doc_type"] or "other"] = cell.get(r["doc_type"] or "other", 0) + r["n"]
            totals["library"] += r["n"]
        if r["status"] in totals and r["status"] != "library":
            totals[r["status"]] += r["n"]
    procs = processes(conn)
    empty = [p for p in procs if p != "other" and p not in grid]
    return {"processes": procs, "types": K.TYPES, "grid": grid, "totals": totals, "empty_processes": empty}


# ---------------------------------------------------------------- checks and numbering (14b)

CHECK_COLS = ("id, sha256, status, doc_type, process, number, title, revision, effective_date, refs, original_name, "
              "path, supersedes")


def process_info(conn) -> dict[str, dict]:
    return {r["code"]: {"name": r["name"], "short": r["short"]}
            for r in conn.execute("select code, name, short from doc_processes order by sort, code")}


def number_rules(conn) -> dict[str, dict]:
    return {r["doc_type"]: r for r in conn.execute("select * from doc_number_rules")}


def check(conn) -> dict:
    """Everything the checks need, computed once: issues, conventions and the process codes in numbers."""
    docs = conn.execute(f"select {CHECK_COLS} from documents where status <> 'rejected' order by id").fetchall()  # noqa: S608
    procs = process_info(conn)
    codes = CK.process_codes(docs, procs)
    convs = CK.conventions(docs, number_rules(conn))
    return {"docs": docs, "processes": procs, "codes": codes, "conventions": convs,
            "issues": CK.issues(docs, procs, convs, codes)}


SINGLE = {   # issues listed for many documents at once, as they read on one document's page
    "no_date": ("No effective date", "The file shows none; add it if it is known, otherwise the approval date will be "
                                     "used"),
    "form_unused": ("No records of this form yet", "No filled-in record of this form is in the library"),
}


def suggestions(conn, doc: dict, state: dict | None = None) -> dict:
    """The suggested number (when it has none or one off the convention) and standard file name of a document."""
    state = state or check(conn)
    mine = [dict(i, docs=[doc["id"]], title=SINGLE[i["kind"]][0], detail=SINGLE[i["kind"]][1]) if i["kind"] in SINGLE
            else i for i in state["issues"] if doc["id"] in i["docs"]]
    number = next((i["suggest"] for i in mine if i["kind"] in ("no_number", "odd_number") and i.get("suggest")), None)
    return {"number": number, "file_name": CK.standard_name(dict(doc, number=doc["number"] or number)),
            "issues": mine}


def set_rule(conn, email: str, doc_type: str, template: str, digits: int) -> dict:
    if doc_type not in CK.NUMBERED:
        raise DocError(say("numbering rules are for procedures, work instructions, forms and specifications"))
    template = (template or "").strip().upper().replace("{PROCESS}", "{process}").replace("{SEQ}", "{seq}")
    if template.count("{seq}") != 1 or not template.endswith("{seq}") or not re.fullmatch(
            r"[A-Z0-9._/-]*(\{process\}[A-Z0-9._/-]*)?\{seq\}", template):
        raise DocError(say("a rule looks like QP-{seq} or F-{process}-{seq}: letters, digits and - before {seq} at "
                           "the end"))
    try:
        digits = int(digits)
    except (TypeError, ValueError) as exc:
        raise DocError(say("the sequence number has 1 to 6 digits")) from exc
    if not 1 <= digits <= 6:
        raise DocError(say("the sequence number has 1 to 6 digits"))
    return conn.execute("insert into doc_number_rules (doc_type, template, digits, updated_by) values (%s, %s, %s, %s) "
                        "on conflict (doc_type) do update set template = excluded.template, digits = excluded.digits, "
                        "updated_by = excluded.updated_by, updated_at = now() returning *",
                        (doc_type, template, int(digits), email)).fetchone()


def clear_rule(conn, doc_type: str) -> None:
    conn.execute("delete from doc_number_rules where doc_type = %s", (doc_type,))


def archive(conn, email: str, doc_id: int, reason: str) -> dict:
    """Keep an older revision (or a superseded file) found during import as obsolete: in the library's history, never
    in use. Its file is frozen like any kept document."""
    if not reason.strip():
        raise DocError(say("say why it is kept as obsolete (for example: replaced by rev C)"))
    with conn.transaction():
        doc = _lock(conn, doc_id)
        if doc["status"] not in ("to_classify", "to_review", "draft"):
            raise DocError(say("only a file waiting for review or a draft can be kept as obsolete; make an effective "
                               "document obsolete instead"))
        if doc["supersedes"]:
            raise DocError(say("this is a new revision in progress, not an older one; send it back or leave it"))
        f = {k: doc[k] for k in EDITABLE}
        if not f["doc_type"] or f["process"] not in processes(conn) or not f["title"]:
            raise DocError(say("give it a type, process and title first, so it can be found later"))
        row = conn.execute("update documents set status = 'obsolete', obsolete_reason = %s, fingerprint = sha256, "
                           "confirmed_by = coalesce(confirmed_by, %s), confirmed_at = coalesce(confirmed_at, now()), "
                           "updated_at = now() where id = %s returning *", (reason.strip(), email, doc_id)).fetchone()
        log(conn, doc_id, email, "kept as obsolete", reason.strip())
    return row
