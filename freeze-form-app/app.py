"""
Go Offer — Official Freeze Form generator
Запуск:  streamlit run app.py
"""
from datetime import date
from pathlib import Path
import tempfile, string

import streamlit as st
from freeze_core import (
    FreezeData, render_docx_bytes, docx_bytes_to_html,
    docx_to_pdf, output_filename, _find_soffice,
)

DEFAULT_TEMPLATE = "freeze_template_jinja.docx"

# Метки, которые приложение подставляет. При редактировании шаблона в Word
# эти метки должны сохраняться (ненужные можно убрать, но не переименовывать).
TAGS = {
    "{{ exhibit }}": "Буква доп. соглашения (A, B, C…)",
    "{{ client_name }}": "Имя клиента",
    "{{ selected_plan }}": "План клиента",
    "{{ start_date }}": "Дата создания Хаба",
    "{{ orig_expiration }}": "Изначальная дата окончания",
    "{{ break_start }}": "Дата старта паузы",
    "{{ break_end }}": "Дата окончания паузы (расчёт)",
    "{{ break_days }}": "Длительность паузы в днях",
    "{{ reason }}": "Причина (или N/A)",
    "{{ adjusted_expiration }}": "Новая дата окончания (расчёт)",
}

st.set_page_config(page_title="Freeze Form Generator", page_icon="📄", layout="wide")

# ---------- ШАБЛОН (в сайдбаре) ----------
with st.sidebar:
    st.header("⚙️ Шаблон")
    st.caption(
        "Шаблон — обычный Word-файл с метками `{{ ... }}`. Скачайте, "
        "отредактируйте в Word (сохраняя метки) и загрузите обратно."
    )
    with open(DEFAULT_TEMPLATE, "rb") as f:
        st.download_button("⬇️ Скачать шаблон", f, file_name="freeze_template.docx")
    uploaded_tpl = st.file_uploader("⬆️ Загрузить свой шаблон (.docx)", type=["docx"])
    if uploaded_tpl:
        st.success("Используется загруженный шаблон.")
    with st.expander("Список меток"):
        st.table({"Метка": list(TAGS.keys()), "Значение": list(TAGS.values())})


def active_template() -> str:
    if uploaded_tpl is not None:
        tmp = Path(tempfile.gettempdir()) / "uploaded_freeze_template.docx"
        tmp.write_bytes(uploaded_tpl.getvalue())
        return str(tmp)
    return DEFAULT_TEMPLATE


st.title("📄 Official Freeze Form")

left, right = st.columns([1, 1.3], gap="large")

# ---------- ФОРМА (слева) ----------
with left:
    st.subheader("Данные клиента")
    exhibit = st.selectbox("Exhibit (доп. соглашение)", list(string.ascii_uppercase), index=0)
    client_name = st.text_input("Имя клиента (Full Name)")
    selected_plan = st.text_input("План (Selected Plan)")
    start_date = st.date_input("Дата создания Хаба", value=date.today())
    orig_expiration = st.date_input("Изначальная дата окончания контракта", value=date.today())

    st.subheader("Параметры паузы")
    break_start = st.date_input("Дата старта паузы", value=date.today())
    mode = st.radio("Задать паузу", ["По количеству дней", "По дате окончания"], horizontal=True)
    break_days = break_end = None
    if mode == "По количеству дней":
        break_days = st.number_input("Кол-во дней паузы", min_value=1, max_value=365, value=14, step=1)
    else:
        break_end = st.date_input("Дата окончания паузы", value=break_start)
    reason = st.text_area("Причина паузы (опционально)", placeholder="Если пусто — будет N/A")

# ---------- ПРЕДПРОСМОТР (справа, обновляется сразу) ----------
with right:
    st.subheader("Предпросмотр документа")

    data = err = None
    if client_name.strip() and selected_plan.strip():
        try:
            data = FreezeData(
                client_name=client_name.strip(),
                selected_plan=selected_plan.strip(),
                start_date=start_date,
                orig_expiration=orig_expiration,
                break_start=break_start,
                exhibit=exhibit,
                break_days=int(break_days) if break_days is not None else None,
                break_end=break_end,
                reason=reason,
            )
        except ValueError as e:
            err = str(e)
    else:
        st.info("Заполните имя клиента и план — документ появится здесь.")

    if err:
        st.error(err)

    if data is not None:
        c = data.context()
        m1, m2, m3 = st.columns(3)
        m1.metric("Дней паузы", c["break_days"])
        m2.metric("Окончание паузы", c["break_end"])
        m3.metric("Новая дата окончания", c["adjusted_expiration"])

        try:
            docx_bytes = render_docx_bytes(data, active_template())
            html = docx_bytes_to_html(docx_bytes)
        except Exception as e:
            st.error(f"Ошибка шаблона (проверьте метки): {e}")
            st.stop()

        st.markdown(
            f'<div style="background:#fff;color:#111;border:1px solid #ddd;'
            f'border-radius:8px;padding:28px 34px;font-family:Calibri,Arial,sans-serif;'
            f'line-height:1.5;">{html}</div>',
            unsafe_allow_html=True,
        )

        st.divider()
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "⬇️ Скачать .docx", docx_bytes,
                file_name=output_filename(data, "docx"),
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        with d2:
            if _find_soffice():
                if st.button("📄 Подготовить PDF", use_container_width=True):
                    out_dir = Path(tempfile.mkdtemp())
                    dpath = out_dir / output_filename(data, "docx")
                    dpath.write_bytes(docx_bytes)
                    try:
                        pdf = docx_to_pdf(dpath)
                        st.session_state["pdf_bytes"] = pdf.read_bytes()
                        st.session_state["pdf_name"] = output_filename(data, "pdf")
                    except Exception as e:
                        st.error(f"PDF не создан: {e}")
                if st.session_state.get("pdf_bytes"):
                    st.download_button(
                        "⬇️ Скачать PDF", st.session_state["pdf_bytes"],
                        file_name=st.session_state.get("pdf_name", "freeze.pdf"),
                        mime="application/pdf", use_container_width=True,
                    )
            else:
                st.caption("PDF недоступен (нет LibreOffice).")
