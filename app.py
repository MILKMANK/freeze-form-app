"""
Go Offer Docs — генератор документов по шаблонам.
Запуск:  streamlit run app.py
"""
import json, string
from datetime import date
from pathlib import Path

import streamlit as st
import engine as E
from editor import template_editor

DATA_FILE = Path(__file__).parent / "data.json"
LETTERS = list(string.ascii_uppercase)

# Глобальный словарь переменных (един для всех документов).
DEFAULT_VARS = [
    {"token": "name", "label": "Имя клиента", "type": "text"},
    {"token": "plan", "label": "Выбранный план", "type": "text"},
    {"token": "exhibit", "label": "Exhibit (буква)", "type": "text"},
    {"token": "start_date", "label": "Дата создания Хаба", "type": "date"},
    {"token": "orig_expiration", "label": "Изнач. дата окончания", "type": "date"},
    {"token": "break_start", "label": "Дата старта паузы", "type": "date"},
    {"token": "break_end", "label": "Дата окончания паузы", "type": "date"},
    {"token": "break_days", "label": "Длительность паузы (дней)", "type": "number"},
    {"token": "reason", "label": "Причина", "type": "text"},
    {"token": "adjusted_expiration", "label": "Новая дата окончания", "type": "date"},
    {"token": "current_expiration", "label": "Текущая дата окончания", "type": "date"},
    {"token": "extension_months", "label": "Продление (месяцев)", "type": "number"},
    {"token": "new_expiration", "label": "Новая дата окончания (продление)", "type": "date"},
]

BUILTINS = {
    "freeze": {"name": "Official Freeze Form", "kind": "freeze", "default_text": E.FREEZE_TEXT,
               "var_tokens": ["exhibit", "name", "plan", "start_date", "orig_expiration",
                              "break_start", "break_end", "break_days", "reason", "adjusted_expiration"]},
    "extension": {"name": "Extension of Program Term", "kind": "extension", "default_text": E.EXT_TEXT,
                  "var_tokens": ["exhibit", "name", "plan", "start_date", "current_expiration",
                                 "extension_months", "new_expiration"]},
}
BUILTIN_ORDER = ["freeze", "extension"]


# ---------------- хранилище ----------------
def load_data():
    d = {"texts": {}, "custom_types": [], "saved": {}, "variables": []}
    if DATA_FILE.exists():
        try:
            d.update(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    have = {v["token"] for v in d.get("variables", [])}
    for v in DEFAULT_VARS:
        if v["token"] not in have:
            d.setdefault("variables", []).append(dict(v))
    return d


def save_data():
    try:
        DATA_FILE.write_text(json.dumps(st.session_state.data, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        return True
    except Exception:
        return False


def D():
    return st.session_state.data


def variables():
    return D()["variables"]


def var_get(token):
    for v in variables():
        if v["token"] == token:
            return v
    return {"token": token, "label": token, "type": "text"}


# ---------------- типы ----------------
def all_types():
    out = []
    for k in BUILTIN_ORDER:
        b = BUILTINS[k]
        out.append({"key": k, "name": b["name"], "builtin": True, "kind": b["kind"],
                    "var_tokens": b["var_tokens"]})
    for ct in D()["custom_types"]:
        out.append({"key": ct["key"], "name": ct["name"], "builtin": False, "kind": "custom",
                    "var_tokens": ct.get("var_tokens", [])})
    return out


def get_type(tk):
    for t in all_types():
        if t["key"] == tk:
            return t
    return None


def fields_of(t):
    return [{"key": tok, "label": var_get(tok)["label"], "type": var_get(tok)["type"]}
            for tok in t["var_tokens"]]


def text_of(tk):
    if tk in D()["texts"]:
        return D()["texts"][tk]
    return BUILTINS[tk]["default_text"] if tk in BUILTINS else ""


def vars_panel(t):
    return [[tok, var_get(tok)["label"]] for tok in t["var_tokens"]]


# ---------------- форма / контекст ----------------
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
        flds = fields_of(t)
        if not flds:
            st.info("У этого типа пока нет полей. Добавь их в разделе «шаблон».")
        for f in flds:
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
    return E.compute_custom(fields_of(t), form)


def metrics_of(t, ctx):
    if t["kind"] == "freeze":
        return [("Дней паузы", ctx["break_days"]), ("Окончание паузы", ctx["break_end"]),
                ("Новое окончание", ctx["adjusted_expiration"])]
    if t["kind"] == "extension":
        return [("Продление (мес.)", ctx["extension_months"]), ("Новое окончание", ctx["new_expiration"])]
    return []


# ---------------- предпросмотр (HTML) ----------------
def preview_html(text, ctx, client, with_table=True):
    import re, html as _h
    out = []
    for raw in (text or "").split("\n"):
        line = raw.rstrip("\r")
        if line.startswith("## "):
            content, sty = line[3:], "font-weight:bold;margin:8px 0 2px;"
        elif line.startswith("# "):
            content, sty = line[2:], "text-align:center;font-weight:bold;font-size:15px;margin:2px 0;"
        elif line.strip() == "":
            out.append('<div style="height:8px;"></div>'); continue
        else:
            content, sty = line, "white-space:pre-wrap;line-height:1.5;"
        h = _h.escape(content)
        h = re.sub(r"\*\*([^*]+?)\*\*", r"<strong>\1</strong>", h)
        h = re.sub(r"\*([^*]+?)\*", r"<em>\1</em>", h)
        h = re.sub(r"\{(\w+)\}", lambda m: _h.escape(str(ctx.get(m.group(1), m.group(0)))), h)
        out.append(f'<div style="{sty}">{h or "&nbsp;"}</div>')
    body = "".join(out)
    if with_table:
        rows = [("<b>Provider</b>", "<b>Client</b>", 1),
                ("Go Offer Inc", "Full Name: " + _h.escape(client or ""), 2),
                ("EIN: 93-4028120", "Passport/Driving License:", 2),
                ("Signature:", "Signature:", 4), ("Date:", "Date:", 2)]
        trs = ""
        for a, b, blanks in rows:
            pad = "<br>" * blanks
            trs += (f'<tr><td style="border:1px solid #000;padding:6px 8px;width:50%;vertical-align:top;">{a}{pad}</td>'
                    f'<td style="border:1px solid #000;padding:6px 8px;width:50%;vertical-align:top;">{b}{pad}</td></tr>')
        body += f'<table style="border-collapse:collapse;width:100%;margin-top:12px;">{trs}</table>'
    return (f'<div style="background:#fff;color:#1a1a1a;border:0.5px solid #ccc;border-radius:8px;'
            f'padding:28px 32px;font-family:Arial,sans-serif;font-size:13px;">{body}</div>')


# ---------------- состояние ----------------
st.set_page_config(page_title="Go Offer Docs", page_icon="📄", layout="wide")
if "data" not in st.session_state:
    st.session_state.data = load_data()
for k, v in [("type", "freeze"), ("section", "create"), ("step", 1), ("editor_nonce", 0)]:
    if k not in st.session_state:
        st.session_state[k] = v


def goto(tk, section):
    if tk != st.session_state.type:
        st.session_state.step = 1
    st.session_state.type = tk
    st.session_state.section = section


# ---------------- меню (тоглы) ----------------
with st.sidebar:
    st.markdown("### Документы")
    subs = [("create", "создать документ"), ("template", "шаблон"), ("created", "созданные документы")]
    for t in all_types():
        with st.expander(t["name"].upper(), expanded=(st.session_state.type == t["key"])):
            for sk, sl in subs:
                active = st.session_state.type == t["key"] and st.session_state.section == sk
                if st.button(("• " if active else "") + sl, key=f"nav_{t['key']}_{sk}",
                             use_container_width=True):
                    goto(t["key"], sk); st.rerun()
    st.divider()
    if st.button("➕ Создать новый тип", use_container_width=True):
        n = len(D()["custom_types"]) + 1
        key = f"custom{n}"
        while any(c["key"] == key for c in D()["custom_types"]):
            n += 1; key = f"custom{n}"
        D()["custom_types"].append({"key": key, "name": f"Новый тип документа {n}", "var_tokens": ["name"]})
        D()["texts"][key] = "# НОВЫЙ ДОКУМЕНТ\n\nClient: {name}\n\n(добавь поля и текст ниже)"
        save_data(); goto(key, "template"); st.rerun()

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
            ok = True
            if t["kind"] in ("freeze", "extension"):
                ok = bool(form["client_name"]) and bool(form["selected_plan"])
            if not ok:
                st.error("Заполни имя клиента и план.")
            else:
                r = compute(t, form)
                if r["err"]:
                    st.error(r["err"])
                else:
                    st.session_state.cur_ctx = r["ctx"]
                    st.session_state.step = 2
                    st.rerun()
    else:
        st.caption("Шаг 2 из 2 — предпросмотр и сохранение")
        ctx = st.session_state.cur_ctx
        client = ctx.get("name", "")
        mt = metrics_of(t, ctx)
        if mt:
            cols = st.columns(len(mt))
            for col, (lbl, val) in zip(cols, mt):
                col.metric(lbl, val)
        st.markdown(preview_html(text_of(t["key"]), ctx, client, True), unsafe_allow_html=True)
        st.write("")
        docx_bytes = E.build_docx(text_of(t["key"]), ctx, client)
        fname = f"{E.safe_name(client)}_{t['key']}"
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("← Назад", use_container_width=True):
                st.session_state.step = 1; st.rerun()
        with b2:
            st.download_button("⬇️ .docx", docx_bytes, file_name=fname + ".docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True)
        with b3:
            if st.button("💾 Сохранить", type="primary", use_container_width=True):
                D()["saved"].setdefault(t["key"], []).insert(0, {
                    "client": client or "—", "date": date.today().strftime(E.DATE_FMT),
                    "type_name": t["name"], "text": text_of(t["key"]), "ctx": ctx})
                save_data(); st.success("Сохранено в «созданные документы».")
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
    if not t["builtin"]:
        ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
        ct["name"] = st.text_input("Название типа документа", ct["name"])
        st.markdown("**Поля формы** (переменные документа)")
        rm = None
        for i, tok in enumerate(ct["var_tokens"]):
            c = st.columns([5, 1])
            v = var_get(tok)
            c[0].markdown(f"`{{{tok}}}` — {v['label']} · _{v['type']}_")
            if c[1].button("🗑", key=f"rmv_{t['key']}_{i}"):
                rm = i
        if rm is not None:
            ct["var_tokens"].pop(rm); save_data(); st.rerun()
        with st.expander("➕ Добавить поле"):
            avail = [v for v in variables() if v["token"] not in ct["var_tokens"]]
            opts = ["➕ Создать новую переменную"] + [f"{v['label']}  ·  {{{v['token']}}}" for v in avail]
            choice = st.selectbox("Переменная", opts, key=f"addsel_{t['key']}")
            if choice == "➕ Создать новую переменную":
                nl = st.text_input("Название (метка)", key=f"nl_{t['key']}")
                ntok = st.text_input("Токен (латиницей, без пробелов)", key=f"nt_{t['key']}")
                ntype = st.selectbox("Тип", ["text", "date", "number"], key=f"nty_{t['key']}")
                if st.button("Создать и добавить", key=f"addnew_{t['key']}"):
                    tok = "".join(ch for ch in ntok if ch.isalnum() or ch == "_")
                    if not tok:
                        st.error("Укажи токен.")
                    elif any(v["token"] == tok for v in variables()):
                        st.error("Такой токен уже есть — выбери его из списка.")
                    else:
                        variables().append({"token": tok, "label": nl or tok, "type": ntype})
                        ct["var_tokens"].append(tok); save_data(); st.rerun()
            else:
                if st.button("Добавить", key=f"addex_{t['key']}"):
                    tok = avail[opts.index(choice) - 1]["token"]
                    ct["var_tokens"].append(tok); save_data(); st.rerun()

    st.markdown("**Текст документа** — таблица подписей добавляется автоматически в конце.")
    new_text = template_editor(text=text_of(t["key"]), variables=vars_panel(t),
                               key=f"editor_{t['key']}_{st.session_state.editor_nonce}")
    if new_text is not None:
        D()["texts"][t["key"]] = new_text

    a1, a2 = st.columns(2)
    with a1:
        if st.button("💾 Сохранить шаблон", type="primary", use_container_width=True):
            st.success("Сохранено." if save_data() else "Не удалось записать на диск.")
    with a2:
        if t["builtin"] and st.button("↩️ Сбросить текст", use_container_width=True):
            D()["texts"][t["key"]] = BUILTINS[t["key"]]["default_text"]
            st.session_state.editor_nonce += 1
            save_data(); st.rerun()

    st.markdown("**Предпросмотр**")
    ph = {tok: f"‹{lbl}›" for tok, lbl in vars_panel(t)}
    st.markdown(preview_html(text_of(t["key"]), ph, "‹Имя клиента›", False), unsafe_allow_html=True)

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
                c[0].markdown(f"**{e['client']}**  \n<span style='color:gray;font-size:12px'>"
                              f"{e['date']} · {e['type_name']}</span>", unsafe_allow_html=True)
                client = e["ctx"].get("name", e.get("client", ""))
                docx_bytes = E.build_docx(e["text"], e["ctx"], client)
                fname = f"{E.safe_name(e['client'])}_{t['key']}"
                c[1].download_button("⬇️ .docx", docx_bytes, file_name=fname + ".docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"dl_{t['key']}_{i}", use_container_width=True)
                if E._find_soffice():
                    if c[2].button("PDF", key=f"pdf_{t['key']}_{i}", use_container_width=True):
                        try:
                            st.session_state[f"sp_{t['key']}_{i}"] = E.docx_to_pdf_bytes(docx_bytes)
                        except Exception as ex:
                            st.error(f"PDF не создан: {ex}")
                    if st.session_state.get(f"sp_{t['key']}_{i}"):
                        st.download_button("⬇️ Скачать PDF", st.session_state[f"sp_{t['key']}_{i}"],
                            file_name=fname + ".pdf", mime="application/pdf", key=f"dlp_{t['key']}_{i}")
