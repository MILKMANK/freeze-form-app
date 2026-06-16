"""
Go Offer — Official Freeze Form
Запуск:  streamlit run app.py
"""
from datetime import date
import json, string

import streamlit as st
from freeze_core import FreezeData, docx_bytes_to_html, docx_bytes_to_pdf_bytes, output_filename, _find_soffice
from freeze_doc import build_docx, load_template, save_template, DEFAULT_TEMPLATE

st.set_page_config(page_title="Freeze Form", page_icon="📄", layout="wide")

# ---------- state ----------
if "page" not in st.session_state:
    st.session_state.page = "create"
if "step" not in st.session_state:
    st.session_state.step = 1
if "cfg" not in st.session_state:
    st.session_state.cfg = load_template()
if "ctx" not in st.session_state:
    st.session_state.ctx = None

PAGES = [("create", "➕ Создать документ"), ("final", "✅ Итоговый документ"), ("template", "📝 Шаблон")]


def goto(page):
    st.session_state.page = page
    st.rerun()


def preview_html(html: str):
    st.markdown(
        f'<div style="background:#fff;color:#111;border:1px solid #ddd;border-radius:8px;'
        f'padding:28px 34px;font-family:Arial,sans-serif;line-height:1.5;">{html}</div>',
        unsafe_allow_html=True,
    )


def build_data() -> FreezeData:
    """Собирает FreezeData из значений формы (ключи session_state)."""
    mode = st.session_state.get("break_mode", "По количеству дней")
    return FreezeData(
        client_name=st.session_state.get("cli_name", "").strip(),
        selected_plan=st.session_state.get("cli_plan", "").strip(),
        start_date=st.session_state.get("d_start", date.today()),
        orig_expiration=st.session_state.get("d_orig", date.today()),
        break_start=st.session_state.get("d_break_start", date.today()),
        exhibit=st.session_state.get("cli_exhibit", "A"),
        break_days=int(st.session_state.get("break_days_n", 14)) if mode == "По количеству дней" else None,
        break_end=st.session_state.get("d_break_end") if mode == "По дате окончания" else None,
        reason=st.session_state.get("reason_txt", ""),
    )


# ---------- layout: контент слева, меню справа ----------
content_col, menu_col = st.columns([4, 1.1], gap="large")

with menu_col:
    st.markdown("### Меню")
    for key, label in PAGES:
        kind = "primary" if st.session_state.page == key else "secondary"
        if st.button(label, key=f"nav_{key}", use_container_width=True, type=kind):
            goto(key)
    if _find_soffice() is None:
        st.caption("⚠️ PDF локально недоступен (нет LibreOffice).")

with content_col:
    page = st.session_state.page

    # ===================== СОЗДАТЬ ДОКУМЕНТ =====================
    if page == "create":
        st.title("➕ Создать документ")

        # --- ШАГ 1 ---
        if st.session_state.step == 1:
            st.caption("Шаг 1 из 2 — данные клиента и паузы")
            c1, c2 = st.columns(2)
            with c1:
                st.selectbox("Exhibit (доп. соглашение)", list(string.ascii_uppercase), key="cli_exhibit")
                st.text_input("Имя клиента (Full Name)", key="cli_name")
                st.text_input("План (Selected Plan)", key="cli_plan")
            with c2:
                st.date_input("Дата создания Хаба", key="d_start", value=date.today())
                st.date_input("Изначальная дата окончания контракта", key="d_orig", value=date.today())

            st.subheader("Параметры паузы")
            st.date_input("Дата старта паузы", key="d_break_start", value=date.today())
            st.radio("Задать паузу", ["По количеству дней", "По дате окончания"], key="break_mode", horizontal=True)
            if st.session_state.break_mode == "По количеству дней":
                st.number_input("Кол-во дней паузы", min_value=1, max_value=365, value=14, step=1, key="break_days_n")
            else:
                st.date_input("Дата окончания паузы", key="d_break_end", value=date.today())
            st.text_area("Причина паузы (опционально)", key="reason_txt", placeholder="Если пусто — будет N/A")

            if st.button("Далее → предпросмотр", type="primary"):
                if not st.session_state.get("cli_name", "").strip() or not st.session_state.get("cli_plan", "").strip():
                    st.error("Заполните имя клиента и план.")
                else:
                    try:
                        st.session_state.ctx = build_data().context()
                        st.session_state.step = 2
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        # --- ШАГ 2 ---
        else:
            st.caption("Шаг 2 из 2 — предпросмотр")
            data = build_data()
            ctx = data.context()
            st.session_state.ctx = ctx
            m1, m2, m3 = st.columns(3)
            m1.metric("Дней паузы", ctx["break_days"])
            m2.metric("Окончание паузы", ctx["break_end"])
            m3.metric("Новая дата окончания", ctx["adjusted_expiration"])

            docx_bytes = build_docx(st.session_state.cfg, ctx)
            preview_html(docx_bytes_to_html(docx_bytes))

            st.divider()
            b1, b2 = st.columns(2)
            with b1:
                if st.button("← Назад к данным", use_container_width=True):
                    st.session_state.step = 1
                    st.rerun()
            with b2:
                if st.button("К итоговому документу →", type="primary", use_container_width=True):
                    goto("final")

    # ===================== ИТОГОВЫЙ ДОКУМЕНТ =====================
    elif page == "final":
        st.title("✅ Итоговый документ")
        if st.session_state.ctx is None:
            st.info("Сначала заполните данные в разделе «Создать документ».")
            if st.button("➕ Перейти к созданию", type="primary"):
                st.session_state.step = 1
                goto("create")
        else:
            ctx = st.session_state.ctx
            data = build_data()
            docx_bytes = build_docx(st.session_state.cfg, ctx)
            preview_html(docx_bytes_to_html(docx_bytes))
            st.divider()

            d1, d2 = st.columns(2)
            with d1:
                st.download_button(
                    "⬇️ Скачать .docx", docx_bytes, file_name=output_filename(data, "docx"),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            with d2:
                if _find_soffice():
                    if st.button("📄 Сгенерировать PDF", type="primary", use_container_width=True):
                        try:
                            st.session_state.pdf = docx_bytes_to_pdf_bytes(docx_bytes)
                            st.session_state.pdf_name = output_filename(data, "pdf")
                        except Exception as e:
                            st.error(f"PDF не создан: {e}")
                    if st.session_state.get("pdf"):
                        st.download_button(
                            "⬇️ Скачать PDF", st.session_state.pdf,
                            file_name=st.session_state.get("pdf_name", "freeze.pdf"),
                            mime="application/pdf", use_container_width=True,
                        )
                else:
                    st.caption("PDF недоступен (нет LibreOffice).")

    # ===================== ШАБЛОН =====================
    elif page == "template":
        st.title("📝 Шаблон документа")
        st.caption("Редактируй текст документа. Метки вида {client_name}, {exhibit} и т.п. "
                   "подставляются автоматически и в этих текстах их обычно трогать не нужно.")
        cfg = st.session_state.cfg

        cfg["title2"] = st.text_input("Заголовок формы", cfg["title2"])
        cfg["intro"] = st.text_area("Вступительный абзац", cfg["intro"], height=110)
        cfg["note"] = st.text_area("Примечание о паузе", cfg["note"], height=80)
        cfg["reason_label"] = st.text_input("Подпись к причине паузы", cfg["reason_label"])

        st.subheader("Обязательства клиента")
        new_items = []
        for i, item in enumerate(cfg["ack_items"]):
            with st.container(border=True):
                cols = st.columns([6, 1])
                title = cols[0].text_input("Заголовок пункта", item["title"], key=f"ack_t_{i}")
                remove = cols[1].button("🗑", key=f"ack_del_{i}", help="Удалить пункт")
                body = st.text_area("Текст пункта", item["body"], key=f"ack_b_{i}", height=90)
                if not remove:
                    new_items.append({"title": title, "body": body})
        cfg["ack_items"] = new_items
        if st.button("➕ Добавить пункт"):
            cfg["ack_items"].append({"title": "Новый пункт", "body": "Текст пункта."})
            st.rerun()

        with st.expander("Заголовки секций, метки полей, данные провайдера"):
            cfg["title1"] = st.text_input("Строка Exhibit", cfg["title1"])
            cfg["client_header"] = st.text_input("Заголовок: информация о клиенте", cfg["client_header"])
            cfg["break_header"] = st.text_input("Заголовок: детали паузы", cfg["break_header"])
            cfg["timeline_header"] = st.text_input("Заголовок: новые сроки", cfg["timeline_header"])
            cfg["ack_header"] = st.text_input("Заголовок: обязательства", cfg["ack_header"])
            cfg["ack_intro"] = st.text_area("Вступление к обязательствам", cfg["ack_intro"], height=70)
            for k, lbl in [("field_full_name", "Метка: имя"), ("field_plan", "Метка: план"),
                           ("field_start", "Метка: дата старта программы"),
                           ("field_orig_exp", "Метка: изнач. окончание"),
                           ("field_break_start", "Метка: старт паузы"),
                           ("field_break_end", "Метка: конец паузы"),
                           ("field_break_days", "Метка: длительность"),
                           ("field_adjusted", "Метка: новое окончание")]:
                cfg[k] = st.text_input(lbl, cfg[k])
            cfg["provider_name"] = st.text_input("Провайдер: название", cfg["provider_name"])
            cfg["provider_ein"] = st.text_input("Провайдер: EIN", cfg["provider_ein"])

        st.session_state.cfg = cfg
        st.divider()
        s1, s2, s3 = st.columns(3)
        with s1:
            if st.button("💾 Сохранить шаблон", type="primary", use_container_width=True):
                try:
                    save_template(cfg)
                    st.success("Шаблон сохранён.")
                except Exception as e:
                    st.warning(f"Не удалось записать на диск ({e}). Скачайте JSON для сохранения.")
        with s2:
            st.download_button("⬇️ Экспорт (JSON)", json.dumps(cfg, ensure_ascii=False, indent=2),
                               file_name="template_config.json", mime="application/json",
                               use_container_width=True)
        with s3:
            if st.button("↩️ Сбросить к стандартному", use_container_width=True):
                st.session_state.cfg = json.loads(json.dumps(DEFAULT_TEMPLATE))
                st.rerun()

        up = st.file_uploader("Импорт шаблона (JSON)", type=["json"])
        if up:
            try:
                st.session_state.cfg = json.loads(up.getvalue().decode("utf-8"))
                st.success("Шаблон импортирован. Не забудь «Сохранить».")
            except Exception as e:
                st.error(f"Не удалось прочитать JSON: {e}")
