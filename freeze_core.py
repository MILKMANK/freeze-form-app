"""Расчёты дат, имя файла, конвертация PDF и HTML-предпросмотр."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import subprocess, re, io

DATE_FMT = "%B %d, %Y"          # напр. "March 05, 2026"


@dataclass
class FreezeData:
    client_name: str
    selected_plan: str
    start_date: date
    orig_expiration: date
    break_start: date
    exhibit: str = "A"
    break_end: "date | None" = None
    break_days: "int | None" = None
    reason: str = ""

    def __post_init__(self):
        if self.break_days is None and self.break_end is None:
            raise ValueError("Укажите длительность паузы или дату её окончания.")
        if self.break_end is None:
            if self.break_days < 1:
                raise ValueError("Длительность паузы должна быть не меньше 1 дня.")
            self.break_end = self.break_start + timedelta(days=self.break_days - 1)
        elif self.break_days is None:
            if self.break_end < self.break_start:
                raise ValueError("Дата окончания паузы раньше даты начала.")
            self.break_days = (self.break_end - self.break_start).days + 1
        else:
            self.break_days = (self.break_end - self.break_start).days + 1
        self.adjusted_expiration = self.orig_expiration + timedelta(days=self.break_days)

    def context(self) -> dict:
        return {
            "exhibit": self.exhibit,
            "client_name": self.client_name,
            "selected_plan": self.selected_plan,
            "start_date": self.start_date.strftime(DATE_FMT),
            "orig_expiration": self.orig_expiration.strftime(DATE_FMT),
            "break_start": self.break_start.strftime(DATE_FMT),
            "break_end": self.break_end.strftime(DATE_FMT),
            "break_days": str(self.break_days),
            "reason": self.reason.strip() if self.reason.strip() else "N/A",
            "adjusted_expiration": self.adjusted_expiration.strftime(DATE_FMT),
        }


def _safe(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", s).strip("_") or "client"


def output_filename(data: FreezeData, ext: str) -> str:
    return f"{_safe(data.client_name)}_FreezeForm_Exhibit{_safe(data.exhibit)}.{ext}"


def docx_bytes_to_html(docx_bytes: bytes) -> str:
    import mammoth
    return mammoth.convert_to_html(io.BytesIO(docx_bytes)).value


def _find_soffice() -> "str | None":
    import shutil
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
    ):
        if Path(p).exists():
            return p
    return None


def docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """Конвертирует .docx (bytes) в .pdf (bytes) через LibreOffice."""
    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError("LibreOffice не найден — PDF недоступен.")
    import tempfile
    d = Path(tempfile.mkdtemp())
    src = d / "doc.docx"
    src.write_bytes(docx_bytes)
    subprocess.run(
        [soffice, "--headless",
         "-env:UserInstallation=file:///tmp/lo_freeze_profile",
         "--convert-to", "pdf", "--outdir", str(d), str(src)],
        check=True, capture_output=True,
    )
    pdf = d / "doc.pdf"
    if not pdf.exists():
        raise RuntimeError("PDF не создан — проверьте установку LibreOffice.")
    return pdf.read_bytes()
