"""Ядро генерации Freeze Form: расчёты, валидация, рендер .docx + PDF."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
import subprocess, re

from docxtpl import DocxTemplate

DATE_FMT = "%B %d, %Y"          # напр. "March 05, 2026"


@dataclass
class FreezeData:
    client_name: str
    selected_plan: str
    start_date: date                       # дата создания Хаба
    orig_expiration: date                  # изначальная дата окончания
    break_start: date                      # дата старта паузы
    exhibit: str = "A"                     # A, B, C...
    break_end: date | None = None          # одно из двух:
    break_days: int | None = None          # длительность ИЛИ дата окончания
    reason: str = ""                       # опционально

    warnings: list[str] = field(default_factory=list)

    def __post_init__(self):
        # --- взаимный расчёт break_end <-> break_days ---
        if self.break_days is None and self.break_end is None:
            raise ValueError("Нужно указать либо длительность паузы, либо дату её окончания.")
        if self.break_end is None:
            if self.break_days < 1:
                raise ValueError("Длительность паузы должна быть >= 1 дня.")
            # break_end включительно: start + (days - 1)
            self.break_end = self.break_start + timedelta(days=self.break_days - 1)
        elif self.break_days is None:
            if self.break_end < self.break_start:
                raise ValueError("Дата окончания паузы раньше даты начала.")
            self.break_days = (self.break_end - self.break_start).days + 1
        else:
            # заданы оба — проверяем согласованность
            calc = (self.break_end - self.break_start).days + 1
            if calc != self.break_days:
                self.warnings.append(
                    f"Несогласованность: по датам пауза {calc} дн., указано {self.break_days} дн. "
                    f"Использую расчёт по датам ({calc})."
                )
                self.break_days = calc

        # --- новая дата окончания контракта = старая + дни паузы ---
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


def render_docx(data: FreezeData, template_path: str, out_dir: str) -> Path:
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{_safe(data.client_name)}_FreezeForm_Exhibit{_safe(data.exhibit)}.docx"
    out = out_dir / fname
    tpl = DocxTemplate(template_path)
    tpl.render(data.context())
    tpl.save(out)
    return out


def render_docx_bytes(data: FreezeData, template_path: str) -> bytes:
    """Рендерит заполненный документ в память (.docx как bytes)."""
    import io
    tpl = DocxTemplate(template_path)
    tpl.render(data.context())
    buf = io.BytesIO()
    tpl.save(buf)
    return buf.getvalue()


def docx_bytes_to_html(docx_bytes: bytes) -> str:
    """Конвертирует .docx (bytes) в HTML для предпросмотра в приложении."""
    import io, mammoth
    return mammoth.convert_to_html(io.BytesIO(docx_bytes)).value


def output_filename(data: FreezeData, ext: str) -> str:
    return f"{_safe(data.client_name)}_FreezeForm_Exhibit{_safe(data.exhibit)}.{ext}"


def _find_soffice() -> str | None:
    import shutil
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    # типичные пути на macOS / Windows
    for p in (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
    ):
        if Path(p).exists():
            return p
    return None


def docx_to_pdf(docx_path: Path) -> Path:
    """Конвертирует .docx в .pdf через LibreOffice. Требует установленный LibreOffice."""
    docx_path = Path(docx_path)
    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice не найден. Установите его, чтобы получать PDF "
            "(https://www.libreoffice.org/download)."
        )
    subprocess.run(
        [soffice, "--headless",
         "-env:UserInstallation=file:///tmp/lo_freeze_profile",
         "--convert-to", "pdf",
         "--outdir", str(docx_path.parent), str(docx_path)],
        check=True, capture_output=True,
    )
    pdf = docx_path.with_suffix(".pdf")
    if not pdf.exists():
        raise RuntimeError("PDF не создан — проверьте установку LibreOffice.")
    return pdf


if __name__ == "__main__":
    # тест 1: задана длительность
    d = FreezeData(
        client_name="John Smith", selected_plan="Premium",
        start_date=date(2026, 1, 10), orig_expiration=date(2026, 7, 10),
        break_start=date(2026, 3, 1), break_days=14, exhibit="A", reason="",
    )
    print("CTX:", d.context())
    print("WARN:", d.warnings)
    docx = render_docx(d, "freeze_template_jinja.docx", "out")
    pdf = docx_to_pdf(docx)
    print("DOCX:", docx, "| PDF:", pdf, pdf.stat().st_size, "bytes")

    # тест 2: задана дата окончания
    d2 = FreezeData(
        client_name="Анна Петрова", selected_plan="Standard",
        start_date=date(2026, 2, 1), orig_expiration=date(2026, 8, 1),
        break_start=date(2026, 4, 1), break_end=date(2026, 4, 30), exhibit="B",
        reason="Медицинский отпуск",
    )
    print("CTX2:", d2.context())
