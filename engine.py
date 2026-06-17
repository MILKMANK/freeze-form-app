"""
Движок Go Offer Docs.
- Расчёты дат и контекста для типов документов.
- Рендер текста с разметкой (**жирный**, *курсив*, # H1, ## H2, {переменные}) в .docx.
- Таблица подписей в конце документа (настоящая таблица).
- Конвертация .docx -> .pdf через LibreOffice.
"""
from __future__ import annotations
import io, re, subprocess, shutil, tempfile
from datetime import date, timedelta
from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

DATE_FMT = "%B %d, %Y"
MONTHS = ["January","February","March","April","May","June","July","August",
          "September","October","November","December"]


# ------------- даты -------------
def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    # последний день месяца
    if m == 12:
        last = 31
    else:
        last = (date(y, m + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))


def fmt(d) -> str:
    return d.strftime(DATE_FMT) if d else "—"


def add_duration(d: date, n: int, unit: str) -> date:
    """unit: 'months' или 'days'."""
    return add_months(d, n) if unit == "months" else d + timedelta(days=n)


# типы-длительности и их единица
DURATION_UNIT = {"dur_days": "days", "dur_months": "months"}


def compute_fields(defs: list, form: dict) -> dict:
    """
    Универсальный расчёт по списку переменных.
    defs: [{token,label,type, base?, dur?}], type in
          text|number|date|dur_days|dur_months|calc_date.
    calc_date: дата = (base: дата) + (dur: длительность с её единицей).
    """
    tmap = {v["token"]: v["type"] for v in defs}
    raw, ctx = {}, {}
    for v in defs:
        tok, tp = v["token"], v["type"]
        if tp == "date":
            val = form.get(tok); raw[tok] = val
            ctx[tok] = fmt(val) if val else "—"
        elif tp in ("number", "dur_days", "dur_months"):
            val = form.get(tok)
            n = 0 if val in (None, "") else int(val)
            raw[tok] = n; ctx[tok] = str(n)
        elif tp == "text":
            val = form.get(tok); raw[tok] = val
            ctx[tok] = "" if val in (None, "") else str(val)
    for v in defs:
        if v["type"] == "calc_date":
            base = raw.get(v.get("base"))
            durtok = v.get("dur")
            dur = raw.get(durtok)
            unit = DURATION_UNIT.get(tmap.get(durtok), "days")
            if base:
                d = add_duration(base, int(dur or 0), unit)
                raw[v["token"]] = d; ctx[v["token"]] = fmt(d)
            else:
                ctx[v["token"]] = "—"
    return {"err": None, "ctx": ctx, "raw": raw}


# обратная совместимость
def compute_custom(fields: list, form: dict) -> dict:
    return compute_fields(fields, form)


# ------------- контекст по типам -------------
def compute_freeze(f: dict) -> dict:
    bs, st = f["break_start"], f["start_date"]
    oe = f["orig_exp"]
    if f.get("mode", "days") == "days":
        bd = max(1, int(f.get("break_days") or 1))
        bend = bs + timedelta(days=bd - 1)
        err = None
    else:
        bend = f.get("break_end")
        err = "Дата окончания паузы раньше даты начала." if (bend and bend < bs) else None
        bd = (bend - bs).days + 1 if bend else 0
    adj = oe + timedelta(days=bd) if (oe and bd) else None
    return {"err": err, "ctx": {
        "exhibit": f.get("exhibit", "A"),
        "name": f.get("client_name", ""),
        "plan": f.get("selected_plan", ""),
        "start_date": fmt(st),
        "orig_expiration": fmt(oe),
        "break_start": fmt(bs),
        "break_end": fmt(bend),
        "break_days": str(bd or "—"),
        "reason": (f.get("reason") or "").strip() or "N/A",
        "adjusted_expiration": fmt(adj),
    }, "raw": {
        "start_date": st, "orig_expiration": oe, "break_start": bs, "break_end": bend,
        "break_days": bd, "adjusted_expiration": adj,
    }}


def compute_extension(f: dict) -> dict:
    cur = f["current_exp"]
    m = max(1, int(f.get("ext_months") or 1))
    ne = add_months(cur, m) if cur else None
    return {"err": None, "ctx": {
        "exhibit": f.get("exhibit", "A"),
        "name": f.get("client_name", ""),
        "plan": f.get("selected_plan", ""),
        "start_date": fmt(f["start_date"]),
        "current_expiration": fmt(cur),
        "extension_months": str(m),
        "new_expiration": fmt(ne),
    }, "raw": {
        "start_date": f["start_date"], "current_expiration": cur,
        "extension_months": m, "new_expiration": ne,
    }}


# ------------- дефолтные шаблоны -------------
FREEZE_TEXT = "\n".join([
    "# EXHIBIT {exhibit} TO CAREER SUPPORT SERVICES AGREEMENT",
    "# OFFICIAL FREEZE FORM (PROGRAM PAUSE REQUEST)",
    "",
    'This Official Freeze Form ("Form") is submitted pursuant to Section 16 (Break Policy) '
    'of the Career Support Services Agreement ("Agreement") between Go Offer Inc ("Provider") '
    'and the undersigned client ("Client").',
    "",
    "## CLIENT INFORMATION",
    "Full Name: {name}",
    "Selected Plan: {plan}",
    "Original Program Start Date: {start_date}",
    "Original Contract Expiration Date: {orig_expiration}",
    "",
    "## BREAK (FREEZE) DETAILS",
    "Requested Break Start Date: {break_start}",
    "Requested Break End Date: {break_end}",
    "Total Duration of Break (in calendar days): {break_days}",
    "",
    "*Note: Standard Breaks may not exceed 3 weeks (21 days) without special written mutual "
    "agreement as per Section 16.1(b).*",
    "",
    "Reason for Break Request (Optional but recommended):",
    "{reason}",
    "",
    "## NEW CONTRACT TIMELINE (To be filled by Provider upon approval)",
    "Adjusted Contract Expiration Date: {adjusted_expiration}",
    "",
    "## CLIENT ACKNOWLEDGEMENTS AND BINDING COMMITMENTS",
    "By signing and submitting this Form, the Client acknowledges and agrees to the following:",
    "",
    "**1. No Services During Break**",
    "During the approved Break period, all active services (including application submission, "
    "LinkedIn outreach, mentor calls, and curator support) will be temporarily suspended.",
    "",
    "**2. Continued Obligation for Contingent Fee**",
    "If the Client secures a Placement (receives and accepts a job offer) during the Break period, "
    "the Client remains fully obligated to pay the Contingent Fee as defined in Section 18.3 of the "
    "Agreement, provided the interview process or communication was initiated according to the Offer "
    "Attribution Criteria in Section 37.1.",
    "",
    "**3. No Infractions**",
    "The Client will not receive Infractions under the Code of Conduct (Section 24) for "
    "unresponsiveness during this approved Break period.",
    "",
    "**4. Approval Required**",
    "This requested Break is not valid, and the Contract Expiration Date is not officially adjusted, "
    "until this Form is approved and signed by an authorized representative of Go Offer Inc.",
])

EXT_TEXT = "\n".join([
    "# EXHIBIT {exhibit} TO CAREER SUPPORT SERVICES AGREEMENT",
    "# OFFICIAL EXTENSION OF PROGRAM TERM",
    "",
    'This Extension of Program Term ("Extension") is entered into between Go Offer Inc ("Provider") '
    'and the undersigned client ("Client") to extend the term of the Career Support Services '
    'Agreement ("Agreement").',
    "",
    "## CLIENT INFORMATION",
    "Full Name: {name}",
    "Selected Plan: {plan}",
    "Original Program Start Date: {start_date}",
    "Current Contract Expiration Date: {current_expiration}",
    "",
    "## EXTENSION DETAILS",
    "Extension Length (in months): {extension_months}",
    "New Contract Expiration Date: {new_expiration}",
    "",
    "## CLIENT ACKNOWLEDGEMENTS AND BINDING COMMITMENTS",
    "By signing and submitting this Extension, the Client acknowledges and agrees to the following:",
    "",
    "**1. Continued Services**",
    "All services under the Agreement continue through the new Contract Expiration Date on the same "
    "terms and conditions.",
    "",
    "**2. Fees and Obligations**",
    "Any fees, contingent obligations, or commitments defined in the Agreement remain in full effect "
    "for the extended term.",
    "",
    "**3. Approval Required**",
    "This Extension is not valid, and the Contract Expiration Date is not officially adjusted, until "
    "this Form is approved and signed by an authorized representative of Go Offer Inc.",
])

FREEZE_VARS = [
    ("exhibit", "буква доп. соглашения (A, B, C…)"), ("name", "имя клиента"),
    ("plan", "выбранный план"), ("start_date", "дата создания Хаба"),
    ("orig_expiration", "изначальная дата окончания"), ("break_start", "дата старта паузы"),
    ("break_end", "дата окончания паузы (расчёт)"), ("break_days", "длительность паузы в днях"),
    ("reason", "причина (или N/A)"), ("adjusted_expiration", "новая дата окончания (расчёт)"),
]
EXT_VARS = [
    ("exhibit", "буква доп. соглашения"), ("name", "имя клиента"), ("plan", "выбранный план"),
    ("start_date", "дата создания Хаба"), ("current_expiration", "текущая дата окончания"),
    ("extension_months", "на сколько месяцев продление"), ("new_expiration", "новая дата окончания (расчёт)"),
]

PROVIDER_DEFAULT = {"name": "Go Offer Inc", "ein": "EIN: 93-4028120"}


# ------------- разметка -> docx -------------
def _sub(text: str, ctx: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(ctx.get(m.group(1), m.group(0))), text)


def _split(text: str, marker: str):
    parts = text.split(marker)
    return [(p, i % 2 == 1) for i, p in enumerate(parts)]


def _parse_runs(line: str):
    runs = []
    for bt, bold in _split(line, "**"):
        for it, ital in _split(bt, "*"):
            if it != "":
                runs.append((it, bold, ital))
    return runs


def _add_runs(p, line: str, ctx: dict, base_bold=False, size=None):
    for seg, bold, ital in _parse_runs(line):
        r = p.add_run(_sub(seg, ctx))
        r.bold = bold or base_bold
        r.italic = ital
        if size:
            r.font.size = Pt(size)


def _set_table_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0"); el.set(qn("w:color"), "000000")
        borders.append(el)
    tblPr.append(borders)


# Таблица подписей одинакова во всех документах.
SIG_PROVIDER_NAME = "Go Offer Inc"
SIG_PROVIDER_EIN = "EIN: 93-4028120"


def _signature_table(doc, client_name: str):
    # (left, right, header?, кол-во пустых строк под заполнение)
    rows = [
        ("Provider", "Client", True, 0),
        (SIG_PROVIDER_NAME, f"Full Name: {client_name}", False, 2),
        (SIG_PROVIDER_EIN, "Passport/Driving License:", False, 2),
        ("Signature:", "Signature:", False, 4),
        ("Date:", "Date:", False, 2),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    table.autofit = True
    _set_table_borders(table)
    for ri, (left, right, hdr, blanks) in enumerate(rows):
        for ci, txt in enumerate((left, right)):
            cell = table.cell(ri, ci)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = cell.paragraphs[0].add_run(txt)
            run.bold = hdr
            for _ in range(blanks):
                cell.add_paragraph()
    return table


def build_docx(text: str, ctx: dict, client_name: str) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(11)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Inches(1)

    for raw in (text or "").split("\n"):
        line = raw.rstrip("\r")
        if line.startswith("## "):
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(6)
            _add_runs(p, line[3:], ctx, base_bold=True)
        elif line.startswith("# "):
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_runs(p, line[2:], ctx, base_bold=True, size=14)
        elif line.strip() == "":
            sp = doc.add_paragraph(); sp.paragraph_format.space_after = Pt(4)
        else:
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _add_runs(p, line, ctx)

    doc.add_paragraph()
    _signature_table(doc, client_name)

    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue()


# ------------- pdf -------------
def _find_soffice():
    for n in ("soffice", "libreoffice"):
        p = shutil.which(n)
        if p:
            return p
    for p in ("/Applications/LibreOffice.app/Contents/MacOS/soffice",
              r"C:\Program Files\LibreOffice\program\soffice.exe"):
        if Path(p).exists():
            return p
    return None


def docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    so = _find_soffice()
    if not so:
        raise RuntimeError("LibreOffice не найден — PDF недоступен.")
    d = Path(tempfile.mkdtemp())
    src = d / "doc.docx"; src.write_bytes(docx_bytes)
    subprocess.run([so, "--headless", "-env:UserInstallation=file:///tmp/lo_go_profile",
                    "--convert-to", "pdf", "--outdir", str(d), str(src)],
                   check=True, capture_output=True)
    pdf = d / "doc.pdf"
    if not pdf.exists():
        raise RuntimeError("PDF не создан.")
    return pdf.read_bytes()


def safe_name(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", s or "client").strip("_") or "client"
