"""Fictional quality documents of the demo company (ADR-0014 item 9): procedures, work instructions, forms, records
and certificates, in the formats companies really keep (Word, PDF, Excel, CSV, text and a scanned image).

Problems are built in on purpose so the library has something to find: an older revision of a procedure, an
identical copy of a form, a work instruction without a number, and processes with no documents at all (complaints,
training procedure). Everything is invented; the files are made by code, never copied from a real company.
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile

ROOT = "Harbor Lane QMS"
LABEL = "Demo: Harbor Lane QMS folder"
UPLOADER = "dana@demo.example"
COMPANY = "Harbor Lane Supply (Demo)"


# ---------------------------------------------------------------- file makers

def pdf(lines: list[str]) -> bytes:
    """A plain text PDF (Helvetica, 46 lines a page) without any library."""
    def esc(s: str) -> str:
        return s.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(") \
            .replace(")", "\\)")

    pages = [lines[i:i + 46] for i in range(0, max(1, len(lines)), 46)] or [[]]
    objs: list[bytes] = []
    n_pages = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    font = 3 + 2 * n_pages
    for i, page in enumerate(pages):
        stream = "BT /F1 11 Tf 56 790 Td 15 TL " + " ".join(f"({esc(ln)}) '" for ln in page) + " ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode())
        data = stream.encode("latin-1")
        objs.append(b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def docx(header: list[str], paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    import docx as D  # noqa: PLC0415 - python-docx, a hub dependency

    d = D.Document()
    d.core_properties.author = COMPANY
    hdr = d.sections[0].header
    hdr.paragraphs[0].text = header[0] if header else ""
    for h in header[1:]:
        hdr.add_paragraph(h)
    for p in paragraphs:
        if p.startswith("# "):
            d.add_heading(p[2:], level=1)
        elif p.startswith("## "):
            d.add_heading(p[3:], level=2)
        else:
            d.add_paragraph(p)
    if table:
        t = d.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, v in enumerate(row):
                t.cell(r, c).text = v
    buf = io.BytesIO()
    d.save(buf)
    return _stable_zip(buf.getvalue())


def xlsx(sheets: dict[str, list[list]]) -> bytes:
    import openpyxl  # noqa: PLC0415

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.properties.creator = COMPANY
    buf = io.BytesIO()
    wb.save(buf)
    return _stable_zip(buf.getvalue())


def _stable_zip(data: bytes) -> bytes:
    """Office files are zips with timestamps; fix them so the same document gives the same bytes every time."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for info in src.infolist():
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                import re  # noqa: PLC0415

                body = re.sub(rb"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", b"2026-01-05T09:00:00Z", body)
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 5, 9, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, body)
    return out.getvalue()


def scan(lines: list[str]) -> bytes:
    """A 'scanned' certificate: dark text on an off-white page, as a PNG, read back with OCR."""
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

    img = Image.new("L", (1700, 1100), 246)
    draw = ImageDraw.Draw(img)
    big, small = ImageFont.load_default(size=46), ImageFont.load_default(size=34)
    y = 90
    for i, ln in enumerate(lines):
        f = big if i == 0 else small
        draw.text((110, y), ln, fill=25, font=f)
        y += 78 if i == 0 else 58
    draw.rectangle((60, 50, 1640, 1050), outline=80, width=4)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- content

def _procedure(no: str, title: str, rev: str, eff: str, owner: str, purpose: str, steps: list[str],  # noqa: PLR0917
               records: list[str]) -> tuple[list[str], list[str]]:
    header = [f"{COMPANY} - Quality procedure", f"Doc No.: {no}    Rev: {rev}    Effective date: {eff}"]
    body = [f"# {title}", f"Document owner: {owner}", "## 1. Purpose", purpose, "## 2. Scope",
            "This procedure applies to the Tampa Distribution Center and the Head Office.",
            "## 3. Procedure", *[f"3.{i} {s}" for i, s in enumerate(steps, 1)], "## 4. Records",
            *[f"- {r}" for r in records], "## 5. Revision history", f"Rev {rev}: current issue, effective {eff}."]
    return header, body


def files() -> list[tuple[str, bytes]]:
    """(path inside the import, bytes) for every demo document, deterministic."""
    out: list[tuple[str, bytes]] = []
    P = f"{ROOT}/01 Procedures"

    h, b = _procedure("QP-01", "Control of Documents", "C", "2025-02-03", "Quality Manager",
                      "To make sure the right revision of every document is used and obsolete ones are not.",
                      ["Documents are reviewed and approved by the Quality Manager before use.",
                       "Changes are requested on the Document Change Request F-QA-001.",
                       "The Master Document List F-QA-002 shows the current revision of every document.",
                       "Obsolete documents are removed from points of use or marked OBSOLETE."],
                      ["F-QA-001 Document Change Request", "F-QA-002 Master Document List"])
    out.append((f"{P}/QP-01 Control of Documents Rev C.docx", docx(h, b)))

    h, b = _procedure("QP-04", "Purchasing and Supplier Evaluation", "B", "2025-04-14", "Purchasing Lead",
                      "To buy only from suppliers able to meet our requirements and to watch how they perform.",
                      ["New suppliers are evaluated on the Supplier Evaluation form F-PU-002 before the first order.",
                       "Approved suppliers are listed on the Approved Supplier List F-PU-001.",
                       "Purchase orders state item, quantity, price and required date.",
                       "On-time delivery and rejected lots are reviewed for each supplier every quarter."],
                      ["F-PU-001 Approved Supplier List", "F-PU-002 Supplier Evaluation"])
    out.append((f"{P}/QP-04 Purchasing and Supplier Evaluation Rev B.docx", docx(h, b)))

    h, b = _procedure("QP-05", "Receiving Inspection", "D", "2025-09-08", "Quality Manager",
                      "To check incoming goods against the order and the inspection plan before they are stocked.",
                      ["The receiving clerk checks quantity and labels against the purchase order.",
                       "Items with an inspection plan are sampled and measured; results go on the Receiving "
                       "Inspection Record F-QA-010.",
                       "Rejected lots are moved to QC Hold and a Nonconformance Report F-QA-012 is opened.",
                       "Accepted lots are moved to Main Stock."],
                      ["F-QA-010 Receiving Inspection Record", "F-QA-012 Nonconformance Report"])
    out.append((f"{P}/QP-05 Receiving Inspection Rev D.pdf", pdf(h + b)))

    def qp08(rev: str, eff: str, extra: list[str]) -> bytes:
        h, b = _procedure("QP-08", "Control of Nonconforming Product", rev, eff, "Quality Manager",
                          "To keep nonconforming product from being used or shipped by mistake.",
                          ["Nonconforming product is tagged and moved to QC Hold.",
                           "The finder opens a Nonconformance Report F-QA-012.",
                           "Quality decides the disposition: use as is, rework, return to supplier or scrap.",
                           *extra],
                          ["F-QA-012 Nonconformance Report"])
        return pdf(h + b)

    out.append((f"{P}/QP-08 Control of Nonconforming Product Rev C.pdf",
                qp08("C", "2025-06-02", ["Major nonconformances need a corrective action under QP-09.",
                                         "Use-as-is needs approval by a second person."])))
    out.append((f"{P}/old/QP-08 Control of Nonconforming Product Rev B.pdf",
                qp08("B", "2023-11-20", ["Repeated problems are discussed in the weekly meeting."])))

    h, b = _procedure("QP-09", "Corrective and Preventive Action", "B", "2025-06-02", "Quality Manager",
                      "To find and remove the causes of problems so they do not happen again.",
                      ["A corrective action is requested on the CAPA Request F-QA-014.",
                       "The owner finds the root cause (5 Whys or 8D) and plans actions with due dates.",
                       "Quality checks that the actions worked before the CAPA is closed."],
                      ["F-QA-014 CAPA Request"])
    out.append((f"{P}/QP-09 Corrective and Preventive Action Rev B.docx", docx(h, b)))

    h, b = _procedure("QP-11", "Calibration of Measuring Equipment", "A", "2024-08-19", "Quality Manager",
                      "To make sure gauges used for receiving inspection measure correctly.",
                      ["Every gauge has an ID and is listed on the Calibration Log F-QA-020.",
                       "Gauges are calibrated every 12 months by an accredited laboratory.",
                       "A gauge found out of tolerance is withdrawn and the lots it measured are reviewed."],
                      ["F-QA-020 Calibration Log"])
    out.append((f"{P}/QP-11 Calibration Rev A.docx", docx(h, b)))

    W = f"{ROOT}/02 Work Instructions"
    out.append((f"{W}/WI-WH-03 Picking and Packing.docx", docx(
        [f"{COMPANY} - Work instruction", "Doc No.: WI-WH-03    Rev: 2    Effective date: 2025-05-12"],
        ["# Picking and Packing", "Owner: Warehouse Lead",
         "1. Print the pick list from ERPNext for the sales order.",
         "2. Pick from Main Stock only; never from QC Hold.",
         "3. Pack in the box size on the pick list and seal with packing tape.",
         "4. Print the 4 x 6 shipping label and scan it to confirm the shipment."])))
    out.append((f"{W}/torque check for anchors.txt", (
        b"Torque check for wedge anchors\n\n"
        b"Use the torque wrench (gauge ID TW-02).\n"
        b"Pick 3 anchors from each new lot of ANCHOR-38.\n"
        b"Set the test block and torque to 25 ft-lb.\n"
        b"Write the result on the receiving inspection record.\n")))

    Fm = f"{ROOT}/03 Forms"
    out.append((f"{Fm}/F-QA-010 Receiving Inspection Record.xlsx", xlsx({"Form": [
        ["Receiving Inspection Record", None, None, None, "Form No. F-QA-010", "Rev 3"],
        ["Date", "PO / Receipt", "Item", "Sample size", "Result (accept / reject)", "Inspector"],
        *[[None] * 6 for _ in range(3)]]})))
    ncr_form = docx([f"{COMPANY}", "Form No. F-QA-012    Rev 4"],
                    ["# Nonconformance Report", "NCR number: ________   Date: ________",
                     "Item / lot: ____________________   Quantity: ______",
                     "Description of the nonconformance:", "", "Disposition (circle one): use as is / rework / "
                     "return to supplier / scrap", "Approved by: ____________   Date: ________"])
    out.append((f"{Fm}/F-QA-012 Nonconformance Report.docx", ncr_form))
    out.append((f"{Fm}/copy of F-QA-012 Nonconformance Report.docx", ncr_form))
    out.append((f"{Fm}/F-PU-001 Approved Supplier List.xlsx", xlsx({"Approved suppliers": [
        ["Approved Supplier List", None, None, "Form No. F-PU-001", "Rev 5"],
        ["Supplier", "Supplies", "Approved on", "Certificate", "Status"],
        ["Gulf Fasteners (Demo)", "Fasteners", "2024-03-11", "ISO 9001", "Approved - on watch (late deliveries)"],
        ["Bayline Electrical (Demo)", "Electrical", "2023-09-05", "ISO 9001", "Approved"],
        ["Coastal Packaging (Demo)", "Packaging", "2024-01-22", "-", "Approved"],
        ["Summit Tools (Demo)", "Tools", "2025-02-17", "ISO 9001", "Approved"],
        ["Sunshine Metrology (Demo)", "Calibration services", "2024-11-04", "ISO/IEC 17025", "Approved"]]})))

    R = f"{ROOT}/04 Records/2026"
    out.append((f"{R}/F-QA-020 Calibration Log 2026.xlsx", xlsx({"Log": [
        ["Calibration Log", None, None, None, "Form No. F-QA-020", "Rev 1"],
        ["Gauge ID", "Description", "Calibrated on", "Due", "Result", "Lab"],
        ["CAL-01", "Thread pitch gauge M8", "2026-01-14", "2027-01-14", "Pass", "Sunshine Metrology (Demo)"],
        ["CAL-02", "Digital caliper 0-150 mm", "2026-01-14", "2027-01-14", "Pass", "Sunshine Metrology (Demo)"],
        ["TW-02", "Torque wrench 10-80 ft-lb", "2025-07-03", "2026-07-03", "Pass", "Sunshine Metrology (Demo)"]]})))
    out.append((f"{R}/Receiving inspection HX-BOLT-M8 lot 4471.pdf", pdf([
        "Receiving Inspection Record    Form No. F-QA-010 Rev 3", "",
        "Date: 2026-08-12    Receipt: MAT-PRE-DEMO-0041    Item: HX-BOLT-M8", "Supplier: Gulf Fasteners (Demo)",
        "Sample size: 8    Characteristic: pitch diameter 7.160 - 7.212 mm",
        "Readings: 7.190 7.214 7.188 7.216 7.195 7.213 7.192 7.191",
        "Result: REJECT (3 of 8 above the upper limit)", "Inspector: Jordan Quality",
        "Lot moved to QC Hold; NCR opened."])))
    out.append((f"{R}/Internal audit report 2026-03.docx", docx(
        [f"{COMPANY} - Internal audit report"],
        ["# Internal Audit Report - Receiving and Storage", "Audit date: 2026-03-18    Auditor: Sam Ops",
         "Scope: QP-05 Receiving Inspection and QP-08 Control of Nonconforming Product.",
         "Finding 1 (minor): two receiving records did not show the sample size.",
         "Finding 2 (observation): QC Hold area label is faded.",
         "Follow-up: CAPA requested for finding 1 on F-QA-014."])))
    out.append((f"{R}/Management review minutes 2026-06.docx", docx(
        [f"{COMPANY} - Management review"],
        ["# Management Review Minutes", "Date: 2026-06-24    Chair: Dana Owner",
         "Attendees: Dana Owner, Sam Ops, Jordan Quality, Pat Buyer",
         "Inputs reviewed: on-time delivery, supplier performance, nonconformances, audit results.",
         "Decision: keep Gulf Fasteners (Demo) on watch; review again in Q4.",
         "Decision: start a document library and move all procedures into it."])))
    L = f"{ROOT}/04 Records/Logs"
    out.append((f"{L}/NCR log 2025-2026.xlsx", xlsx({"NCR log": [
        ["Nonconformance log - Harbor Lane Supply (Demo)"],
        ["NCR #", "Date", "Item", "Supplier", "Qty", "Description", "Class", "Disposition", "Status", "Closed"],
        ["NCR-2025-01", "2025-02-11", "HX-BOLT-M8", "Gulf Fasteners (Demo)", 200, "Thread damage on 14 bolts in box 3",
         "Minor", "Return to supplier", "Closed", "2025-02-20"],
        ["NCR-2025-02", "2025-04-03", "CBL-12-50", "Bayline Electrical (Demo)", 5, "Insulation nicked on 2 coils",
         "Minor", "Scrap", "Closed", "2025-04-05"],
        ["NCR-2025-03", "2025-06-17", "BOX-18", "Coastal Packaging (Demo)", 50, "Boxes crushed in delivery", "Minor",
         "Use as is", "Closed", "2025-06-18"],
        ["NCR-2025-04", "2025-09-09", "HX-BOLT-M8", "Gulf Fasteners (Demo)", 400,
         "Pitch diameter above limit on 3 of 8 samples", "Major", "Return to supplier", "Closed", "2025-10-02"],
        ["NCR-2026-01", "2026-01-22", "LEVEL-24", "Summit Tools (Demo)", 12, "Bubble vial misaligned", "Minor", "RTV",
         "Closed", "1/30/2026"],
        ["NCR-2026-02", "2026-03-05", "TAPE-48", "Coastal Packaging (Demo)", 30,
         "Tape does not stick at low temperature", "Minor", None, "Open", None],
        ["NCR-2026-03", "2026-05-14", "WRAP-20", None, None, "Stretch wrap roll damaged in warehouse", "Minor",
         "Scrap", "Cancelled - entered twice", None]]})))
    out.append((f"{L}/CAPA log.xlsx", xlsx({"CAPA": [
        ["CAR No.", "Opened", "Type", "Problem", "Root cause", "Action", "Owner", "NCR Ref", "Status", "Closed"],
        ["CAR-2025-01", "2025-09-12", "Corrective", "Gulf Fasteners bolts out of tolerance",
         "Supplier thread rolling die worn", "Supplier replaced the die; pitch check added to QP-05", "Jordan Quality",
         "NCR-2025-04", "Closed", "2025-12-15"],
        ["CAR-2026-01", "2026-02-02", "Corrective", "Late deliveries from Gulf Fasteners",
         "No safety stock for the key item", "Reorder point set; weekly call with the supplier", "Pat Buyer", None,
         "In progress", None],
        ["PAR-2026-01", "2026-04-20", "Preventive", "Tape adhesion in cold storage", None,
         "Test tape samples before the winter purchase", "Jordan Quality", "NCR-2026-02", "Open", None]]})))
    out.append((f"{ROOT}/04 Records/Training/training records warehouse.csv", (
        b"Name,Course,Date,Trainer,Result\n"
        b"Lee Warehouse,WI-WH-03 Picking and Packing,2025-05-20,Sam Ops,Competent\n"
        b"Lee Warehouse,QP-05 Receiving Inspection (receiving clerk part),2025-09-15,Jordan Quality,Competent\n"
        b"Pat Buyer,QP-04 Purchasing and Supplier Evaluation,2025-04-28,Dana Owner,Competent\n")))

    C = f"{ROOT}/05 Certificates"
    out.append((f"{C}/Bayline Electrical ISO 9001 certificate.png", scan([
        "CERTIFICATE OF REGISTRATION (FICTIONAL)", "This certifies that the quality management system of",
        "Bayline Electrical (Demo)", "has been assessed and found to conform to ISO 9001:2015",
        "Scope: distribution of electrical wiring products", "Certificate No. DEMO-QMS-20417",
        "Valid until: 2027-09-30", "Issued by: Example Registrar (Demo)"])))
    out.append((f"{C}/CoC Summit Tools lot 2208.pdf", pdf([
        "CERTIFICATE OF CONFORMANCE", "Summit Tools (Demo)", "",
        "Customer: Harbor Lane Supply (Demo)    PO: PUR-ORD-DEMO-0117", "Item: Tape measure 25 ft (TAPE-MEAS-25)",
        "Lot: 2208    Quantity: 120", "We certify that the goods above conform to the purchase order and to our",
        "product specification TM-25 Rev 6.", "Signed: Quality Department, Summit Tools (Demo)    Date: 2026-07-09"])))
    return out


def load(conn, manifest: dict, today, model=None) -> dict:
    """Import the demo folder as Dana (the owner) would, take its text and classify it (with the model when the
    company has a key, else by the rules). Nothing is confirmed: that is for people. Once only."""
    from wqops.hub.docs import ai_classify as AIC  # noqa: PLC0415
    from wqops.hub.docs import library as LIB  # noqa: PLC0415

    if not manifest.get("demo"):
        raise ValueError("demo documents are only loaded into a company manifest marked demo: true")
    done = conn.execute("select id from doc_imports where label = %s", (LABEL,)).fetchone()
    if done:
        return {"import": done["id"], "loaded": False}
    imp = LIB.new_import(conn, UPLOADER, LABEL)
    for path, data in files():
        LIB.add_file(conn, imp["id"], path, data)
    LIB.extract_import(conn, imp["id"])
    out = AIC.run(conn, {"email": UPLOADER, "roles": ["owner"]}, imp["id"], model, today=today,
                  company=manifest["company"]["name"])
    return {"import": imp["id"], "loaded": True, "files": out["files"], "by_model": out["by_model"],
            "by_rules": out["by_rules"]}


def main() -> int:
    """python -m wqops.demo.documents: add the demo documents to a demo installation loaded before they existed."""
    from wqops import company as C  # noqa: PLC0415
    from wqops.hub import db as DB  # noqa: PLC0415
    from wqops.hub.ai import llm as L  # noqa: PLC0415
    from wqops.hub.ont import api as OA  # noqa: PLC0415

    manifest = C.load(os.environ["WQO_COMPANY_FILE"])
    if not manifest.get("demo"):
        print("demo documents are only loaded into a company manifest marked demo: true", file=sys.stderr)
        return 1
    with DB.connect(os.environ["WQO_DB"]) as conn:
        DB.migrate(conn)
        print(json.dumps(load(conn, manifest, OA.today(manifest), L.Anthropic()), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
