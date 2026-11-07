"""Model configuration, step 26c (ADR-0026): a base machine (a made assembly with a released BOM) has option
groups; each option adds, removes or replaces parts of the base BOM; rules say which options require or exclude
others. Generating a model checks the rules (code, not AI), makes an ordinary ERPNext item coded base code + option
codes and a draft BOM (base BOM with the options' edits) that a person releases. The same choice makes one model
only. When the configuration changes, models whose BOM no longer matches are listed for a design change.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from wqops.erp import ErpClient
from wqops.hub.plm import boms as B
from wqops.hub.plm import parts as PT
from wqops.hub.plm import rules as R
from wqops.i18n import say

PlmError = PT.PlmError
CODE = re.compile(r"^[A-Z0-9]{1,4}$")
MAX_GROUPS, MAX_OPTIONS, MAX_EDITS, MAX_RULES = 12, 20, 40, 100


def _base(conn, pid: int) -> dict:
    p = PT.get(conn, pid)
    if p["source"] != "make" or p["category"] != "assembly":
        raise PlmError(say("models are configured on a made assembly"))
    return p


def released_bom(conn, pid: int) -> dict | None:
    return conn.execute("select * from plm_boms where part_id = %s and status = 'released' order by id desc limit 1",
                        (pid,)).fetchone()


# ---- reading

def load(conn, pid: int) -> dict:
    """The configuration as codes: {groups: [{code, name, options: [{code, name, edits: [...]}]}], rules: [...]}."""
    groups = []
    for g in conn.execute("select * from plm_option_groups where base_id = %s order by pos", (pid,)).fetchall():
        opts = []
        for o in conn.execute("select * from plm_options where group_id = %s order by pos", (g["id"],)).fetchall():
            edits = [{"action": e["action"], "code": e["code"], "with": e["with_code"],
                      "qty": None if e["qty"] is None else R.qty_text(e["qty"])}
                     for e in conn.execute("select e.action, e.qty, p.item_code as code, w.item_code as with_code "
                                           "from plm_option_edits e join plm_parts p on p.id = e.part_id left join "
                                           "plm_parts w on w.id = e.with_id where e.option_id = %s order by e.pos",
                                           (o["id"],))]
            opts.append({"code": o["code"], "name": o["name"], "edits": edits})
        groups.append({"code": g["code"], "name": g["name"], "options": opts})
    rules = [{"kind": r["kind"], "a": f"{r['ag']}/{r['ao']}", "b": f"{r['bg']}/{r['bo']}"}
             for r in conn.execute("select r.kind, ga.code as ag, oa.code as ao, gb.code as bg, ob.code as bo "
                                   "from plm_option_rules r join plm_options oa on oa.id = r.a_option join "
                                   "plm_option_groups ga on ga.id = oa.group_id join plm_options ob on ob.id = "
                                   "r.b_option join "
                                   "plm_option_groups gb on gb.id = ob.group_id where r.base_id = %s order by r.id",
                                   (pid,))]
    return {"groups": groups, "rules": rules}


def models(conn, pid: int) -> list[dict]:
    rows = conn.execute("select m.*, p.item_code, p.name, p.status from plm_models m join plm_parts p "
                        "on p.id = m.part_id where m.base_id = %s order by p.item_code", (pid,)).fetchall()
    cfg = load(conn, pid)
    base = released_bom(conn, pid)
    out = []
    for m in rows:
        bom = conn.execute("select id, revision, status from plm_boms where part_id = %s order by id desc limit 1",
                           (m["part_id"],)).fetchone()
        x = {"id": m["id"], "part_id": m["part_id"], "code": m["item_code"], "name": m["name"],
             "status": m["status"], "choice": m["choice"], "bom": dict(bom) if bom else None}
        try:
            want = compose(conn, cfg, m["choice"], base)
            have = B.lines(conn, bom["id"]) if bom else []
            x["differs"] = R.diff(have, want)
        except PlmError as exc:
            x["differs"] = None
            x["problem"] = str(exc)
        out.append(x)
    return out


def view(conn, pid: int) -> dict:
    _base(conn, pid)
    base = released_bom(conn, pid)
    return {"config": load(conn, pid), "models": models(conn, pid),
            "base_bom": {"id": base["id"], "revision": base["revision"]} if base else None}


# ---- saving the configuration (replaced as a whole)

def _code(v, what: str) -> str:
    c = str(v or "").strip().upper()
    if not CODE.match(c):
        raise PlmError(say("{what}: a code is 1 to 4 letters or digits", what=what))
    return c


def _part(conn, code, what: str) -> dict:
    p = PT.by_code(conn, str(code or "").strip())
    if p is None:
        raise PlmError(say("{what}: no such part {code}", what=what, code=code or ""))
    return p


def save(conn, user: dict, pid: int, data: dict) -> dict:  # noqa: PLR0912, PLR0915 - one check after another
    base = _base(conn, pid)
    groups = data.get("groups") if isinstance(data, dict) else None
    rules = data.get("rules") or []
    if not isinstance(groups, list) or len(groups) > MAX_GROUPS or not isinstance(rules, list) or \
            len(rules) > MAX_RULES:
        raise PlmError(say("up to {g} option groups and {r} rules", g=MAX_GROUPS, r=MAX_RULES))
    clean, seen_g, where = [], set(), {}
    for g in groups:
        if not isinstance(g, dict):
            raise PlmError(say("an option group is a name, a code and options"))
        gc = _code(g.get("code"), say("group {name}", name=g.get("name") or ""))
        if gc in seen_g:
            raise PlmError(say("two groups have the code {code}", code=gc))
        seen_g.add(gc)
        gname = str(g.get("name") or "").strip()[:60]
        opts = g.get("options") or []
        if not gname or not isinstance(opts, list) or not 1 <= len(opts) <= MAX_OPTIONS:
            raise PlmError(say("group {code}: a name and 1 to {n} options", code=gc, n=MAX_OPTIONS))
        copts, seen_o = [], set()
        for o in opts:
            if not isinstance(o, dict):
                raise PlmError(say("group {code}: an option is a name, a code and edits", code=gc))
            oc = _code(o.get("code"), say("group {code}", code=gc))
            if oc in seen_o:
                raise PlmError(say("group {g}: two options have the code {code}", g=gc, code=oc))
            seen_o.add(oc)
            oname = str(o.get("name") or "").strip()[:60]
            if not oname:
                raise PlmError(say("option {g}/{o}: give it a name", g=gc, o=oc))
            edits = o.get("edits") or []
            if not isinstance(edits, list) or len(edits) > MAX_EDITS:
                raise PlmError(say("option {g}/{o}: up to {n} changes", g=gc, o=oc, n=MAX_EDITS))
            cedits = []
            for e in edits:
                label = f"{gc}/{oc}"
                act = (e or {}).get("action")
                if act not in ("add", "remove", "replace"):
                    raise PlmError(say("option {label}: a change adds, removes or replaces a part", label=label))
                p = _part(conn, e.get("code"), label)
                if p["id"] == pid:
                    raise PlmError(say("option {label}: the base machine is not in its own BOM", label=label))
                w = _part(conn, e.get("with"), label) if act == "replace" else None
                q = None
                if act == "add" or (act == "replace" and e.get("qty") not in (None, "")):
                    try:
                        q = R.qty(e.get("qty"))
                    except ValueError as exc:
                        raise PlmError(say("option {label}: {error}", label=label, error=str(exc))) from exc
                cedits.append((act, p["id"], w["id"] if w else None, q))
            copts.append((oc, oname, cedits))
            where[f"{gc}/{oc}"] = None
        clean.append((gc, gname, copts))
    crules = []
    for r in rules:
        if not isinstance(r, dict) or r.get("kind") not in ("requires", "excludes"):
            raise PlmError(say("a rule is: A requires B, or A excludes B"))
        a, b = str(r.get("a") or "").strip().upper(), str(r.get("b") or "").strip().upper()
        if a not in where or b not in where:
            raise PlmError(say("rule {a} {kind} {b}: name options as group/option, e.g. T/T",
                               a=a, kind=say("rule::" + r["kind"]), b=b))
        if a.split("/")[0] == b.split("/")[0]:
            raise PlmError(say("rule {a} {kind} {b}: options of one group exclude each other already",
                               a=a, kind=say("rule::" + r["kind"]), b=b))
        crules.append((r["kind"], a, b))
    with conn.transaction():
        conn.execute("select id from plm_parts where id = %s for update", (pid,))
        conn.execute("delete from plm_option_rules where base_id = %s", (pid,))
        conn.execute("delete from plm_option_groups where base_id = %s", (pid,))
        ids = {}
        for gi, (gc, gname, copts) in enumerate(clean, start=1):
            gid = conn.execute("insert into plm_option_groups (base_id, code, name, pos) values (%s, %s, %s, %s) "
                               "returning id", (pid, gc, gname, gi)).fetchone()["id"]
            for oi, (oc, oname, cedits) in enumerate(copts, start=1):
                oid = conn.execute("insert into plm_options (group_id, code, name, pos) values (%s, %s, %s, %s) "
                                   "returning id", (gid, oc, oname, oi)).fetchone()["id"]
                ids[f"{gc}/{oc}"] = oid
                for ei, (act, part_id, with_id, q) in enumerate(cedits, start=1):
                    conn.execute("insert into plm_option_edits (option_id, action, part_id, with_id, qty, pos) "
                                 "values (%s, %s, %s, %s, %s, %s)", (oid, act, part_id, with_id, q, ei))
        for kind, a, b in crules:
            conn.execute("insert into plm_option_rules (base_id, kind, a_option, b_option) values (%s, %s, %s, %s)",
                         (pid, kind, ids[a], ids[b]))
        PT.log(conn, "config", pid, user["email"], "configuration saved",
               say("{g} groups, {r} rules", g=len(clean), r=len(crules)))
    del base
    return view(conn, pid)


# ---- generating a model

def check_choice(cfg: dict, choice) -> dict[str, str]:
    """One option of every group, and the rules kept. Returns the choice cleaned."""
    if not isinstance(choice, dict):
        raise PlmError(say("choose one option in every group"))
    out = {}
    for g in cfg["groups"]:
        c = str(choice.get(g["code"]) or "").strip().upper()
        if c not in {o["code"] for o in g["options"]}:
            raise PlmError(say("choose an option for {name}", name=g["name"]))
        out[g["code"]] = c
    picked = {f"{g}/{o}" for g, o in out.items()}
    for r in cfg["rules"]:
        if r["kind"] == "requires" and r["a"] in picked and r["b"] not in picked:
            raise PlmError(say("rule: {a} requires {b}", a=r["a"], b=r["b"]))
        if r["kind"] == "excludes" and r["a"] in picked and r["b"] in picked:
            raise PlmError(say("rule: {a} and {b} cannot be chosen together", a=r["a"], b=r["b"]))
    return out


def compose(conn, cfg: dict, choice: dict, base_bom: dict | None) -> list[dict]:
    """The model's lines: the released base BOM with the chosen options' edits, in group order."""
    if base_bom is None:
        raise PlmError(say("the base machine needs a released BOM"))
    lines = {x["code"]: dict(x) for x in B.lines(conn, base_bom["id"])}
    names = {}
    for g in cfg["groups"]:
        o = next((o for o in g["options"] if o["code"] == choice.get(g["code"])), None)
        if o is None:
            raise PlmError(say("choose an option for {name}", name=g["name"]))
        for e in o["edits"]:
            label = f"{g['code']}/{o['code']}"
            if e["action"] == "remove":
                if e["code"] not in lines:
                    raise PlmError(say("option {label} removes {code}, which the BOM does not have", label=label,
                                       code=e["code"]))
                del lines[e["code"]]
            elif e["action"] == "replace":
                old = lines.pop(e["code"], None)
                if old is None:
                    raise PlmError(say("option {label} replaces {code}, which the BOM does not have", label=label,
                                       code=e["code"]))
                q = Decimal(e["qty"]) if e["qty"] else Decimal(old["qty"])
                _add(conn, lines, names, e["with"], q)
            else:
                _add(conn, lines, names, e["code"], Decimal(e["qty"]))
    return [lines[k] for k in sorted(lines, key=lambda k: (lines[k].get("pos") or 10**6, k))]


def _add(conn, lines: dict, names: dict, code: str, q: Decimal) -> None:
    if code in lines:
        lines[code]["qty"] = R.qty_text(Decimal(lines[code]["qty"]) + q)
        return
    if code not in names:
        names[code] = PT.by_code(conn, code)
    p = names[code]
    lines[code] = {"code": code, "name": p["name"], "qty": R.qty_text(q), "uom": p["uom"], "part_id": p["id"],
                   "pos": None}


def choice_key(choice: dict) -> str:
    return hashlib.sha256(json.dumps(choice, sort_keys=True).encode()).hexdigest()[:16]


def generate(conn, user: dict, pid: int, choice, erp: ErpClient) -> dict:
    base = _base(conn, pid)
    cfg = load(conn, pid)
    if not cfg["groups"]:
        raise PlmError(say("set up the option groups first"))
    ch = check_choice(cfg, choice)
    have = conn.execute("select part_id from plm_models where base_id = %s and choice_key = %s",
                        (pid, choice_key(ch))).fetchone()
    if have:
        return {"model": have["part_id"], "existing": True}
    bom = released_bom(conn, pid)
    lines = compose(conn, cfg, ch, bom)
    code = f"{base['item_code']}-{''.join(ch[g['code']] for g in cfg['groups'])}"
    name = f"{base['name']} " + " / ".join(next(o["name"] for o in g["options"] if o["code"] == ch[g["code"]])
                                         for g in cfg["groups"])
    if PT.by_code(conn, code):
        raise PlmError(say("part {code} already exists", code=code))
    p = PT.create(conn, user, {"name": name[:140], "category": "assembly", "source": "make", "uom": base["uom"],
                               "code": code, "params": {"model": code},
                               "description": say("model of {base}: {choice}", base=base["item_code"],
                                                  choice=", ".join(f"{k}={v}" for k, v in ch.items())),
                               "confirm_new": True}, erp)
    with conn.transaction():
        conn.execute("insert into plm_models (base_id, part_id, choice, choice_key, base_bom_id, created_by) values "
                     "(%s, %s, %s::jsonb, %s, %s, %s)", (pid, p["id"], json.dumps(ch), choice_key(ch), bom["id"],
                                                          user["email"]))
        PT.log(conn, "config", pid, user["email"], "model generated", code)
    b = B.start(conn, user, p["id"])
    B.set_lines(conn, user, b["bom"]["id"], [{"code": x["code"], "qty": x["qty"], "uom": x["uom"]} for x in lines],
                note=say("generated from {base} BOM rev {rev}", base=base["item_code"], rev=bom["revision"]))
    return {"model": p["id"], "existing": False, "bom": b["bom"]["id"]}
