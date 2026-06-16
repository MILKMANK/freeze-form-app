"""
Go Offer Docs — генератор документов по шаблонам.
Запуск:  streamlit run app.py
"""
import json, copy, string
from datetime import date
from pathlib import Path

import streamlit as st
import engine as E

DATA_FILE = Path(__file__).parent / "data.json"
LETTERS = list(string.ascii_uppercase)

BUILTINS = {
    "freeze": {"name": "Official Freeze Form", "kind": "freeze",
               "vars": E.FREEZE_VARS, "default_text": E.FREEZE_TEXT},
    "extension": {"name": "Extension of Program Term", "kind": "extension",
                  "vars": E.EXT_VARS, "default_text": E.EXT_TEXT},
}
BUILTIN_ORDER = ["freeze", "extension"]


# ---------------- хранилище ----------------
def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"texts": {}, "providers": {}, "custom_types": [], "saved": {}}


def save_data():
    try:
        DATA_FILE.write_text(json.dumps(st.session_state.data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return True
    except Exception:
        return False


def D():
    return st.session_state.data


# ---------------- типы ----------------
def all_types():
    out = []
    for k in BUILTIN_ORDER:
        b = BUILTINS[k]
        out.append({"key": k, "name": b["name"], "builtin": True, "kind": b["kind"], "vars": b["vars"]})
    for ct in D()["custom_types"]:
        out.append({"key": ct["key"], "name": ct["name"], "builtin": False, "kind": "custom",
                    "fields": ct["fields"],
                    "vars": [(f["key"], f["label"] + (" (дата)" if f["type"] == "date" else "")) for f in ct["fields"]]})
    return out


def get_type(tk):
    for t in all_types():
        if t["key"] == tk:
            return t
    return None


def text_of(tk):
    if tk in D()["texts"]:
        return D()["texts"][tk]
    if tk in BUILTINS:
        return BUILTINS[tk]["default_text"]
    return ""


def provider_of(tk):
    p = D()["providers"].get(tk)
    return p if p else dict(E.PROVIDER_DEFAULT)


def client_key(t):
    if t["kind"] in ("freeze", "extension"):
        return "client_name"
    for f in t.get("fields", []):
        if f["key"] == "client_name":
            return "client_name"
    txts = [f for f in t.get("fields", []) if f["type"] == "text"]
    return txts[0]["key"] if txts else None


# ---------------- предпросмотр (HTML) ----------------
def _md_inline(s):
    import re
    s = re.sub(r"\*\*([^*]+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+?)\*", r"<em>\1</em>", s)
    return s


def preview_html(text, ctx, provider, client, with_table=True):
    import re, html as _h
    out = []
    for raw in (text or "").split("\n"):
        line = raw.rstrip("\r")
        if line.startswith("## "):
            tag, content, st_ = "h2", line[3:], "font-weight:bold;margin:8px 0 2px;"
        elif line.startswith("# "):
            tag, content, st_ = "h1", line[2:], "text-align:center;font-weight:bold;font-size:15px;margin:2px 0;"
        elif line.strip() == "":
            out.append('<div style="height:8px;"></div>'); continue
        else:
            tag, content, st_ = "p", line, "white-space:pre-wrap;line-height:1.5;"
        h = _md_inline(_h.escape(content))
        h = re.sub(r"\{(\w+)\}", lambda m: _h.escape(str(ctx.get(m.group(1), m.group(0)))), h)
        out.append(f'<div style="{st_}">{h or "&nbsp;"}</div>')
    body = "".join(out)
    if with_table:
        pn = re.sub(r"\{(\w+)\}", lambda m: str(ctx.get(m.group(1), m.group(0))), provider["name"])
        pe = re.sub(r"\{(\w+)\}", lambda m: str(ctx.get(m.group(1), m.group(0))), provider["ein"])
        rows = [("<b>Provider</b>", "<b>Client</b>"), (_h.escape(pn), "Full Name: " + _h.escape(client)),
                (_h.escape(pe), "Passport/Driving License:"),
                ("Signature:<br><br>", "Signature:<br><br>"), ("Date:<br><br>", "Date:<br><br>")]
        trs = "".join(f'<tr><td style="border:1px solid #000;padding:6px 8px;width:50%;">{a}</td>'
                      f'<td style="border:1px solid #000;padding:6px 8px;width:50%;">{b}</td></tr>' for a, b in rows)
        body += f'<table style="border-collapse:collapse;width:100%;margin-top:12px;">{trs}</table>'
    return (f'<div style="background:#fff;color:#1a1a1a;border:0.5px solid #ccc;border-radius:8px;'
            f'padding:28px 32px;font-family:Arial,sans-serif;font-size:13px;">{body}</div>')


# ---------------- форма и контекст ----------------
def _ensure(k, v):
    if k not in st.session_state:
        st.session_state[k] = v


def _mark(k):
    st.session_state[k] = True


def linked_expiration(ns, start_key, label):
    exp_key, tch = ns + "exp", ns + "exp_touched"
    _ensure(exp_key, E.add_months(st.session_state[start_key], 6))
    _ensure(tch, False)
    if not st.session_state[tch]:
        st.session_state[exp_key] = E.add_months(st.session_state[start_key], 6)
    return st.date_input(label, key=exp_key, on_change=_mark, args=(tch,))


def render_form(t):
    ns = t["key"] + "_"
    kind = t["kind"]
    if kind in ("freeze", "extension"):
        c1, c2 = st.columns(2)
        with c1:
            st.selectbox("Exhibit (доп. соглашение)", LETTERS, key=ns + "exhibit")
            st.text_input("Имя клиента (Full Name)", key=ns + "client_name")
            st.text_input("План (Selected Plan)", key=ns + "selected_plan")
        with c2:
            _ensure(ns + "start", date.today())
            st.date_input("Дата создания Хаба", key=ns + "start")
        if kind == "freeze":
            orig_exp = linked_expiration(ns, ns + "start", "Изнач. дата окончания (по умолч. +6 мес.)")
            st.subheader("Параметры паузы")
            _ensure(ns + "bstart", date.today())
            st.date_input("Дата старта паузы", key=ns + "bstart")
            mode = st.radio("Как задать паузу", ["По количеству дней", "По дате окончания"],
                            key=ns + "mode", horizontal=True)
            if mode == "По количеству дней":
                st.number_input("Кол-во дней паузы", 1, 365, 14, 1, key=ns + "bdays")
                bend = None
            else:
                _ensure(ns + "bend", date.today())
                bend = st.date_input("Дата окончания паузы", key=ns + "bend")
            st.text_area("Причина паузы (опционально)", key=ns + "reason",
                         placeholder="Если пусто — N/A")
            return {"exhibit": st.session_state[ns + "exhibit"],
                    "client_name": st.session_state[ns + "client_name"].strip(),
                    "selected_plan": st.session_state[ns + "selected_plan"].strip(),
                    "start_date": st.session_state[ns + "start"], "orig_exp": orig_exp,
                    "break_start": st.session_state[ns + "bstart"],
                    "mode": "days" if mode == "По количеству дней" else "enddate",
                    "break_days": st.session_state.get(ns + "bdays", 14), "break_end": bend,
                    "reason": st.session_state.get(ns + "reason", "")}
        else:
            cur = linked_expiration(ns, ns + "start", "Текущая дата окончания (по умолч. +6 мес.)")
            st.subheader("Параметры продления")
            st.number_input("Продлить на (месяцев)", 1, 120, 6, 1, key=ns + "months")
            return {"exhibit": st.session_state[ns + "exhibit"],
                    "client_name": st.session_state[ns + "client_name"].strip(),
                    "selected_plan": st.session_state[ns + "selected_plan"].strip(),
                    "start_date": st.session_state[ns + "start"], "current_exp": cur,
                    "ext_months": st.session_state[ns + "months"]}
    else:
        form = {}
        for f in t["fields"]:
            key = ns + f["key"]
            if f["type"] == "date":
                _ensure(key, date.today())
                form[f["key"]] = st.date_input(f["label"], key=key)
            elif f["type"] == "number":
                form[f["key"]] = st.number_input(f["label"], value=0, key=key)
            else:
                form[f["key"]] = st.text_input(f["label"], key=key)
        return form


def compute(t, form):
    if t["kind"] == "freeze":
        return E.compute_freeze(form)
    if t["kind"] == "extension":
        return E.compute_extension(form)
    return E.compute_custom(t["fields"], form)


def metrics_of(t, ctx):
    if t["kind"] == "freeze":
        return [("Дней паузы", ctx["break_days"]), ("Окончание паузы", ctx["break_end"]),
                ("Новое окончание", ctx["adjusted_expiration"])]
    if t["kind"] == "extension":
        return [("Продление (мес.)", ctx["extension_months"]), ("Новое окончание", ctx["new_expiration"])]
    return []


# ---------------- состояние ----------------
st.set_page_config(page_title="Go Offer Docs", page_icon="📄", layout="wide")
if "data" not in st.session_state:
    st.session_state.data = load_data()
if "type" not in st.session_state:
    st.session_state.type = "freeze"
if "section" not in st.session_state:
    st.session_state.section = "create"
if "step" not in st.session_state:
    st.session_state.step = 1


def goto(tk, section):
    if tk != st.session_state.type:
        st.session_state.step = 1
    st.session_state.type = tk
    st.session_state.section = section


# ---------------- меню ----------------
with st.sidebar:
    st.markdown("### Документы")
    subs = [("create", "создать документ"), ("template", "шаблон"), ("created", "созданные документы")]
    for t in all_types():
        st.markdown(f"**{t['name'].upper()}**")
        for sk, sl in subs:
            active = st.session_state.type == t["key"] and st.session_state.section == sk
            if st.button(("• " if active else "") + sl, key=f"nav_{t['key']}_{sk}", use_container_width=True):
                goto(t["key"], sk)
                st.rerun()
    st.divider()
    if st.button("➕ Создать новый тип", use_container_width=True):
        n = len(D()["custom_types"]) + 1
        key = f"custom{n}"
        while any(c["key"] == key for c in D()["custom_types"]):
            n += 1; key = f"custom{n}"
        D()["custom_types"].append({"key": key, "name": f"Новый тип документа {n}",
            "fields": [{"key": "exhibit", "label": "Exhibit", "type": "text"},
                       {"key": "client_name", "label": "Имя клиента", "type": "text"},
                       {"key": "date1", "label": "Дата", "type": "date"}]})
        D()["texts"][key] = "# НОВЫЙ ДОКУМЕНТ\n\nClient: {client_name}\nExhibit: {exhibit}\nDate: {date1}\n\n(настрой поля и текст в разделе «шаблон»)"
        save_data()
        goto(key, "template")
        st.rerun()

# ---------------- контент ----------------
t = get_type(st.session_state.type)
sec = st.session_state.section

if t is None:
    st.warning("Тип документа не найден."); st.stop()

# ===== СОЗДАТЬ =====
if sec == "create":
    st.title(f"{t['name']} — создать")
    if st.session_state.step == 1:
        st.caption("Шаг 1 из 2 — данные")
        form = render_form(t)
        if st.button("Далее — предпросмотр →", type="primary"):
            ck = client_key(t)
            req_ok = True
            if t["kind"] in ("freeze", "extension"):
                req_ok = bool(form["client_name"]) and bool(form["selected_plan"])
            if not req_ok:
                st.error("Заполни имя клиента и план.")
            else:
                r = compute(t, form)
                if r["err"]:
                    st.error(r["err"])
                else:
                    st.session_state.cur_form = form
                    st.session_state.cur_ctx = r["ctx"]
                    st.session_state.step = 2
                    st.rerun()
    else:
        st.caption("Шаг 2 из 2 — предпросмотр и сохранение")
        form = st.session_state.cur_form
        ctx = st.session_state.cur_ctx
        ck = client_key(t)
        client = str(form.get(ck, "")) if ck else ""
        prov = provider_of(t["key"])
        mt = metrics_of(t, ctx)
        if mt:
            cols = st.columns(len(mt))
            for col, (lbl, val) in zip(cols, mt):
                col.metric(lbl, val)
        st.markdown(preview_html(text_of(t["key"]), ctx, prov, client, True), unsafe_allow_html=True)
        st.write("")
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("← Назад", use_container_width=True):
                st.session_state.step = 1; st.rerun()
        docx_bytes = E.build_docx(text_of(t["key"]), ctx, prov["name"], prov["ein"], client)
        fname = f"{E.safe_name(client)}_{t['key']}"
        with b2:
            st.download_button("⬇️ .docx", docx_bytes, file_name=fname + ".docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True)
        with b3:
            if st.button("💾 Сохранить", type="primary", use_container_width=True):
                D()["saved"].setdefault(t["key"], []).insert(0, {
                    "client": client or "—", "date": date.today().strftime(E.DATE_FMT),
                    "type_name": t["name"], "text": text_of(t["key"]), "ctx": ctx, "provider": prov})
                save_data()
                st.success("Сохранено в «созданные документы».")
        if E._find_soffice():
            if st.button("📄 Сгенерировать PDF"):
                try:
                    st.session_state.pdf = E.docx_to_pdf_bytes(docx_bytes)
                    st.session_state.pdf_name = fname + ".pdf"
                except Exception as e:
                    st.error(f"PDF не создан: {e}")
            if st.session_state.get("pdf"):
                st.download_button("⬇️ Скачать PDF", st.session_state.pdf,
                    file_name=st.session_state.get("pdf_name", "doc.pdf"), mime="application/pdf")
        else:
            st.caption("PDF недоступен (нет LibreOffice).")

# ===== ШАБЛОН =====
elif sec == "template":
    st.title(f"{t['name']} — шаблон")
    left, right = st.columns([2, 1], gap="large")
    with right:
        st.markdown("**Переменные**")
        st.caption("Вставляй в текст в фигурных скобках.")
        for tok, desc in t["vars"]:
            st.markdown(f"`{{{tok}}}` — {desc}")
    with left:
        if not t["builtin"]:
            ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
            ct["name"] = st.text_input("Название типа документа", ct["name"])
            st.markdown("**Поля формы**")
            remove_idx = None
            for i, fd in enumerate(ct["fields"]):
                c = st.columns([3, 2, 2, 1])
                fd["label"] = c[0].text_input("Подпись", fd["label"], key=f"cl_{t['key']}_{i}", label_visibility="collapsed")
                fd["key"] = c[1].text_input("токен", fd["key"], key=f"ck_{t['key']}_{i}", label_visibility="collapsed").replace(" ", "")
                fd["type"] = c[2].selectbox("тип", ["text", "date", "number"],
                    index=["text", "date", "number"].index(fd["type"]), key=f"ct_{t['key']}_{i}", label_visibility="collapsed")
                if c[3].button("🗑", key=f"cd_{t['key']}_{i}"):
                    remove_idx = i
            if remove_idx is not None:
                ct["fields"].pop(remove_idx); save_data(); st.rerun()
            if st.button("➕ Добавить поле"):
                ct["fields"].append({"key": f"field{len(ct['fields'])+1}", "label": "Новое поле", "type": "text"})
                save_data(); st.rerun()

        st.markdown("**Текст документа**")
        st.caption("Разметка: `**жирный**`, `*курсив*`, `# Заголовок`, `## Подзаголовок`. "
                   "Таблица подписей добавляется автоматически в конце.")
        txt = st.text_area("Текст", text_of(t["key"]), height=420, key=f"txt_{t['key']}",
                           label_visibility="collapsed")
        D()["texts"][t["key"]] = txt

        prov = provider_of(t["key"])
        pc1, pc2 = st.columns(2)
        prov["name"] = pc1.text_input("Провайдер (название)", prov["name"], key=f"pn_{t['key']}")
        prov["ein"] = pc2.text_input("Провайдер (EIN)", prov["ein"], key=f"pe_{t['key']}")
        D()["providers"][t["key"]] = prov

        a1, a2 = st.columns(2)
        with a1:
            if st.button("💾 Сохранить шаблон", type="primary", use_container_width=True):
                st.success("Сохранено." if save_data() else "Не удалось записать на диск.")
        with a2:
            if t["builtin"] and st.button("↩️ Сбросить текст", use_container_width=True):
                D()["texts"][t["key"]] = BUILTINS[t["key"]]["default_text"]
                save_data(); st.rerun()

        st.markdown("**Предпросмотр**")
        ph_ctx = {tok: f"‹{tok}›" for tok, _ in t["vars"]}
        st.markdown(preview_html(txt, ph_ctx, prov, "‹name›", False), unsafe_allow_html=True)

# ===== СОЗДАННЫЕ =====
elif sec == "created":
    st.title(f"{t['name']} — созданные документы")
    saved = D()["saved"].get(t["key"], [])
    if not saved:
        st.info("Пока пусто. Создай и сохрани документ.")
    else:
        for i, e in enumerate(saved):
            with st.container(border=True):
                c = st.columns([4, 1, 1])
                c[0].markdown(f"**{e['client']}**  \n<span style='color:gray;font-size:12px'>{e['date']} · {e['type_name']}</span>",
                              unsafe_allow_html=True)
                docx_bytes = E.build_docx(e["text"], e["ctx"], e["provider"]["name"], e["provider"]["ein"], e["client"])
                fname = f"{E.safe_name(e['client'])}_{t['key']}"
                c[1].download_button("⬇️ .docx", docx_bytes, file_name=fname + ".docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"dl_{t['key']}_{i}", use_container_width=True)
                if E._find_soffice():
                    if c[2].button("PDF", key=f"pdf_{t['key']}_{i}", use_container_width=True):
                        try:
                            st.session_state[f"spdf_{t['key']}_{i}"] = E.docx_to_pdf_bytes(docx_bytes)
                        except Exception as ex:
                            st.error(f"PDF не создан: {ex}")
                    if st.session_state.get(f"spdf_{t['key']}_{i}"):
                        st.download_button("⬇️ Скачать PDF", st.session_state[f"spdf_{t['key']}_{i}"],
                            file_name=fname + ".pdf", mime="application/pdf", key=f"dlpdf_{t['key']}_{i}")
