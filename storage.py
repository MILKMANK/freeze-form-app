"""
Хранение данных приложения.
Если в st.secrets настроен Google-доступ (gcp_service_account + gsheets.spreadsheet),
данные хранятся в Google-таблице (весь JSON, разбитый на части по ячейкам столбца A
листа "data"). Иначе — в локальном файле data.json (на бесплатном хостинге сбрасывается
при перезапуске).
"""
import json
from pathlib import Path

import streamlit as st

CHUNK = 40000  # символов на ячейку (лимит ячейки Google Sheets ~50k)


def gsheets_configured() -> bool:
    try:
        return "gcp_service_account" in st.secrets and "gsheets" in st.secrets
    except Exception:
        return False


def gdrive_configured() -> bool:
    try:
        return ("gcp_service_account" in st.secrets and "gdrive" in st.secrets
                and bool(st.secrets["gdrive"].get("folder")))
    except Exception:
        return False


def check_gsheets():
    """(ok, сообщение) — пытается реально открыть таблицу и прочитать лист."""
    if not gsheets_configured():
        return False, "В Secrets нет [gcp_service_account] или [gsheets]."
    try:
        ws = _worksheet()
        ws.col_values(1)
        return True, "Таблица открыта, чтение/запись доступны."
    except Exception as e:
        return False, str(e)


def check_gdrive():
    """(ok, сообщение) — проверяет доступ к папке Google Drive."""
    if not gdrive_configured():
        return False, "В Secrets нет [gdrive].folder."
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive"])
        svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        folder = st.secrets["gdrive"]["folder"]
        meta = svc.files().get(fileId=folder, fields="id,name",
                               supportsAllDrives=True).execute()
        return True, f"Папка доступна: {meta.get('name')}"
    except Exception as e:
        return False, str(e)


def upload_to_drive(filename: str, data: bytes, mime: str):
    """Загружает файл в папку Google Drive (folder из secrets). Возвращает ссылку или None."""
    import io
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"])
    svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder = st.secrets["gdrive"]["folder"]
    meta = {"name": filename, "parents": [folder]}
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    f = svc.files().create(body=meta, media_body=media, fields="id,webViewLink",
                           supportsAllDrives=True).execute()
    return f.get("webViewLink")


def _worksheet():
    import gspread
    from google.oauth2.service_account import Credentials
    info = dict(st.secrets["gcp_service_account"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sid = st.secrets["gsheets"]["spreadsheet"]
    sh = gc.open_by_url(sid) if str(sid).startswith("http") else gc.open_by_key(sid)
    try:
        return sh.worksheet("data")
    except Exception:
        return sh.add_worksheet(title="data", rows=300, cols=1)


def load(local_file: Path):
    """Возвращает (data|None, source) — source: 'gsheets'|'local'|'empty'."""
    if gsheets_configured():
        try:
            ws = _worksheet()
            blob = "".join(ws.col_values(1))
            if blob.strip():
                return json.loads(blob), "gsheets"
            return None, "gsheets"
        except Exception as e:
            st.warning(f"Не удалось прочитать Google-таблицу ({e}). Использую локальные данные.")
    if local_file.exists():
        try:
            return json.loads(local_file.read_text(encoding="utf-8")), "local"
        except Exception:
            return None, "empty"
    return None, "empty"


def save(data: dict, local_file: Path) -> str:
    """Сохраняет данные. Возвращает 'gsheets' | 'local' | 'error'."""
    blob = json.dumps(data, ensure_ascii=False)
    if gsheets_configured():
        try:
            ws = _worksheet()
            ws.clear()
            chunks = [blob[i:i + CHUNK] for i in range(0, len(blob), CHUNK)] or [""]
            for i, c in enumerate(chunks):
                ws.update_cell(i + 1, 1, c)
            return "gsheets"
        except Exception as e:
            st.warning(f"Не удалось сохранить в Google-таблицу ({e}). Сохраняю локально.")
    try:
        local_file.write_text(blob, encoding="utf-8")
        return "local"
    except Exception:
        return "error"
