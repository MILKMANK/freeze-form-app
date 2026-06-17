"""
Go Offer Docs — генератор документов по шаблонам.
Запуск:  streamlit run app.py
"""
import json, string
from datetime import date
from pathlib import Path

import streamlit as st
import engine as E
import storage
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
DEFAULT_TOKENS = {v["token"] for v in DEFAULT_VARS}

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
    d = {"texts": {}, "custom_types": [], "saved": {}, "variables": [], "extra_tokens": {},
         "type_created": {}, "archived": {}}
    loaded, src = storage.load(DATA_FILE)
    st.session_state["storage_src"] = src
    if loaded:
        d.update(loaded)
    have = {v["token"] for v in d.get("variables", [])}
    for v in DEFAULT_VARS:
        if v["token"] not in have:
            d.setdefault("variables", []).append(dict(v))
    # миграция старых типов: гарантируем наличие var_tokens
    for ct in d.get("custom_types", []):
        if "var_tokens" not in ct:
            toks = []
            for f in ct.get("fields", []):
                tok = f.get("key") or f.get("token")
                if not tok:
                    continue
                toks.append(tok)
                if not any(v["token"] == tok for v in d.get("variables", [])):
                    d.setdefault("variables", []).append(
                        {"token": tok, "label": f.get("label", tok), "type": f.get("type", "text")})
            ct["var_tokens"] = toks
        ct.pop("fields", None)
    d.setdefault("extra_tokens", {})
    d.setdefault("archived", {})
    tc = d.setdefault("type_created", {})
    today_iso = date.today().isoformat()
    for k in BUILTIN_ORDER:
        tc.setdefault(k, today_iso)
    for ct in d.get("custom_types", []):
        tc.setdefault(ct["key"], today_iso)
    return d


def save_data():
    src = storage.save(st.session_state.data, DATA_FILE)
    st.session_state["storage_src"] = src
    return src != "error"


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
    arch = D().get("archived", {})
    out = []
    for k in BUILTIN_ORDER:
        if k in arch:
            continue
        b = BUILTINS[k]
        out.append({"key": k, "name": b["name"], "builtin": True, "kind": b["kind"],
                    "var_tokens": b["var_tokens"]})
    for ct in D()["custom_types"]:
        if ct["key"] in arch:
            continue
        out.append({"key": ct["key"], "name": ct["name"], "builtin": False, "kind": "custom",
                    "var_tokens": ct.get("var_tokens", [])})
    return out


def type_name(key):
    if key in BUILTINS:
        return BUILTINS[key]["name"]
    for ct in D()["custom_types"]:
        if ct["key"] == key:
            return ct["name"]
    return key


def fmt_iso(s):
    try:
        y, m, dd = s.split("-")
        return f"{dd}.{m}.{y}"
    except Exception:
        return s or "—"


def archive_type(key):
    D().setdefault("archived", {})[key] = date.today().isoformat()


def restore_type(key):
    D().setdefault("archived", {}).pop(key, None)


@st.cache_data(show_spinner=False)
def cached_pdf(text, ctx_json, client):
    ctx = json.loads(ctx_json)
    return E.docx_to_pdf_bytes(E.build_docx(text, ctx, client))


def get_type(tk):
    for t in all_types():
        if t["key"] == tk:
            return t
    return None


def fields_of(t):
    out = []
    for tok in t["var_tokens"]:
        v = var_get(tok)
        out.append({"key": tok, "token": tok, "label": v["label"], "type": v["type"],
                    "base": v.get("base"), "dur": v.get("dur")})
    return out


def base_tokens(t):
    return list(BUILTINS[t["key"]]["var_tokens"]) if t["builtin"] else list(t["var_tokens"])


def extra_tokens(t):
    return D().setdefault("extra_tokens", {}).get(t["key"], [])


def all_tokens(t):
    seen = []
    for tok in base_tokens(t) + extra_tokens(t):
        if tok not in seen:
            seen.append(tok)
    return seen


def add_token_to_type(t, tok):
    if t["builtin"]:
        lst = D().setdefault("extra_tokens", {}).setdefault(t["key"], [])
        if tok not in lst and tok not in base_tokens(t):
            lst.append(tok)
    else:
        ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
        ct.setdefault("var_tokens", [])
        if tok not in ct["var_tokens"]:
            ct["var_tokens"].append(tok)


def remove_token_from_type(t, tok):
    """Убирает переменную из набора документа (базовые встроенные не трогаем)."""
    if t["builtin"]:
        lst = D().setdefault("extra_tokens", {}).get(t["key"], [])
        if tok in lst:
            lst.remove(tok)
    else:
        ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
        if tok in ct.get("var_tokens", []):
            ct["var_tokens"].remove(tok)


def variable_usage(token):
    """Где используется переменная: [(имя типа, кол-во в тексте, есть в полях)]."""
    res = []
    for t in all_types():
        txt = text_of(t["key"])
        cnt = txt.count("{" + token + "}") if isinstance(txt, str) else 0
        intok = token in all_tokens(t)
        if cnt > 0 or intok:
            res.append((t["name"], cnt, intok))
    return res


def delete_variable_everywhere(token):
    """Полное удаление: из реестра, из всех типов и из всех текстов."""
    toks = {token}
    for v in variables():  # каскад: вычисляемые даты, ссылающиеся на токен
        if v.get("type") == "calc_date" and (v.get("base") == token or v.get("dur") == token):
            toks.add(v["token"])
    D()["variables"] = [v for v in variables() if v["token"] not in toks]
    for ct in D()["custom_types"]:
        ct["var_tokens"] = [x for x in ct.get("var_tokens", []) if x not in toks]
    for k in list(D().get("extra_tokens", {}).keys()):
        D()["extra_tokens"][k] = [x for x in D()["extra_tokens"][k] if x not in toks]
    for k, txt in list(D()["texts"].items()):
        if isinstance(txt, str):
            for tk in toks:
                txt = txt.replace("{" + tk + "}", "")
            D()["texts"][k] = txt


def text_of(tk):
    if tk in D()["texts"]:
        v = D()["texts"][tk]
    else:
        v = BUILTINS[tk]["default_text"] if tk in BUILTINS else ""
    if isinstance(v, dict):  # на случай ранее сохранённого объекта {text, cmd}
        v = v.get("text", "")
        D()["texts"][tk] = v
    return v if isinstance(v, str) else ""


def vars_panel(t):
    return [[tok, var_get(tok)["label"]] for tok in all_tokens(t)]


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


def _render_extra(t, ns):
    extra = {}
    toks = [tk for tk in extra_tokens(t)]
    shown = [tk for tk in toks if var_get(tk)["type"] != "calc_date"]
    if shown:
        st.markdown("**Дополнительные поля**")
    for tok in toks:
        v = var_get(tok)
        tp = v["type"]
        if tp == "calc_date":
            continue  # вычисляется автоматически
        key = ns + "x_" + tok
        if tp == "date":
            _ensure(key, date.today())
            extra[tok] = st.date_input(v["label"], key=key)
        elif tp in ("number", "dur_days", "dur_months"):
            lbl = v["label"] + (" (дней)" if tp == "dur_days" else " (мес.)" if tp == "dur_months" else "")
            extra[tok] = st.number_input(lbl, value=0, step=1, key=key)
        else:
            extra[tok] = st.text_input(v["label"], key=key)
    return extra


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
            form = {"exhibit": st.session_state[ns + "exhibit"],
                    "client_name": st.session_state[ns + "client_name"].strip(),
                    "selected_plan": st.session_state[ns + "selected_plan"].strip(),
                    "start_date": st.session_state[ns + "start"], "orig_exp": orig_exp,
                    "break_start": st.session_state[ns + "bstart"],
                    "mode": "days" if mode == "По количеству дней" else "enddate",
                    "break_days": st.session_state.get(ns + "bdays", 14), "break_end": bend,
                    "reason": st.session_state.get(ns + "reason", "")}
            return form, _render_extra(t, ns)
        else:
            cur = linked_expiration(ns, ns + "start", "Текущая дата окончания (по умолч. +6 мес.)")
            st.subheader("Параметры продления")
            st.number_input("Продлить на (месяцев)", 1, 120, 6, 1, key=ns + "months")
            form = {"exhibit": st.session_state[ns + "exhibit"],
                    "client_name": st.session_state[ns + "client_name"].strip(),
                    "selected_plan": st.session_state[ns + "selected_plan"].strip(),
                    "start_date": st.session_state[ns + "start"], "current_exp": cur,
                    "ext_months": st.session_state[ns + "months"]}
            return form, _render_extra(t, ns)
    else:
        form = {}
        flds = fields_of(t)
        inputs = [f for f in flds if f["type"] != "calc_date"]
        if not inputs:
            st.info("У этого типа пока нет полей для ввода. Добавь их в разделе «шаблон».")
        for f in flds:
            tp = f["type"]
            if tp == "calc_date":
                continue
            key = ns + f["key"]
            if tp == "date":
                _ensure(key, date.today())
                form[f["key"]] = st.date_input(f["label"], key=key)
            elif tp in ("number", "dur_days", "dur_months"):
                lbl = f["label"] + (" (дней)" if tp == "dur_days" else " (мес.)" if tp == "dur_months" else "")
                form[f["key"]] = st.number_input(lbl, value=0, step=1, key=key)
            else:
                form[f["key"]] = st.text_input(f["label"], key=key)
        return form, {}


def compute_full(t, form, extra):
    r = compute(t, form)
    if r["err"]:
        return r
    ctx = dict(r["ctx"]); raw = dict(r.get("raw", {}))
    for tok, val in (extra or {}).items():
        raw[tok] = val
        vt = var_get(tok)["type"]
        if vt == "date":
            ctx[tok] = E.fmt(val) if val else "—"
        else:
            ctx[tok] = "" if val in (None, "") else str(val)
    for tok in extra_tokens(t):
        v = var_get(tok)
        if v["type"] == "calc_date":
            base = raw.get(v.get("base")); durtok = v.get("dur"); dur = raw.get(durtok)
            unit = E.DURATION_UNIT.get(var_get(durtok)["type"], "days") if durtok else "days"
            if base and dur not in (None, ""):
                d = E.add_duration(base, int(dur), unit)
                raw[tok] = d; ctx[tok] = E.fmt(d)
            else:
                ctx[tok] = "—"
    return {"err": None, "ctx": ctx}


def compute(t, form):
    if t["kind"] == "freeze":
        return E.compute_freeze(form)
    if t["kind"] == "extension":
        return E.compute_extension(form)
    return E.compute_fields(fields_of(t), form)


def metrics_of(t, ctx):
    if t["kind"] == "freeze":
        return [("Дней паузы", ctx["break_days"]), ("Окончание паузы", ctx["break_end"]),
                ("Новое окончание", ctx["adjusted_expiration"])]
    if t["kind"] == "extension":
        return [("Продление (мес.)", ctx["extension_months"]), ("Новое окончание", ctx["new_expiration"])]
    return []


# ---------------- предпросмотр (HTML) ----------------
def preview_html(text, ctx, client, with_table=True, highlight_vars=False):
    import re, html as _h
    def _repl(m):
        tok = m.group(1)
        val = ctx.get(tok, m.group(0))
        if highlight_vars:
            return ('<span style="background:#ede9fe;color:#7c3aed;border-radius:4px;'
                    'padding:0 4px;">' + _h.escape(str(val)) + '</span>')
        return _h.escape(str(val))
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
        h = re.sub(r"\{(\w+)\}", _repl, h)
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


def _password_set():
    try:
        return bool(st.secrets.get("app_password"))
    except Exception:
        return False


def check_password():
    if not _password_set():
        return True  # пароль не задан (локальная разработка) — открыто
    if st.session_state.get("auth_ok"):
        return True
    st.title("Go Offer Docs")
    st.caption("Вход для сотрудников")
    pw = st.text_input("Пароль", type="password", key="pw_input")
    if st.button("Войти", type="primary"):
        if pw == st.secrets["app_password"]:
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("Неверный пароль.")
    return False


if not check_password():
    st.stop()

if "data" not in st.session_state:
    st.session_state.data = load_data()
for k, v in [("type", "freeze"), ("section", "create"), ("step", 1), ("editor_nonce", 0),
             ("last_cmd_id", None), ("pending_del_var", None)]:
    if k not in st.session_state:
        st.session_state[k] = v


def goto(tk, section):
    if tk != st.session_state.type:
        st.session_state.step = 1
    st.session_state.type = tk
    st.session_state.section = section


def _ser(v):
    return v.isoformat() if isinstance(v, date) else v


def serialize_form(form, extra):
    return ({k: _ser(v) for k, v in (form or {}).items()},
            {k: _ser(v) for k, v in (extra or {}).items()})


def _parse(v):
    try:
        if isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":
            return date.fromisoformat(v)
    except Exception:
        pass
    return v


def repopulate(t, form, extra):
    """Загружает сохранённые данные документа обратно в форму создания."""
    ns = t["key"] + "_"
    f = form or {}
    ex = extra or {}
    if t["kind"] == "freeze":
        st.session_state[ns + "exhibit"] = f.get("exhibit", "A")
        st.session_state[ns + "client_name"] = f.get("client_name", "")
        st.session_state[ns + "selected_plan"] = f.get("selected_plan", "")
        st.session_state[ns + "start"] = _parse(f.get("start_date")) or date.today()
        st.session_state[ns + "exp"] = _parse(f.get("orig_exp")) or date.today()
        st.session_state[ns + "exp_touched"] = True
        st.session_state[ns + "bstart"] = _parse(f.get("break_start")) or date.today()
        st.session_state[ns + "mode"] = "По количеству дней" if f.get("mode") == "days" else "По дате окончания"
        st.session_state[ns + "bdays"] = int(f.get("break_days") or 14)
        if f.get("break_end"):
            st.session_state[ns + "bend"] = _parse(f.get("break_end"))
        st.session_state[ns + "reason"] = f.get("reason", "")
    elif t["kind"] == "extension":
        st.session_state[ns + "exhibit"] = f.get("exhibit", "A")
        st.session_state[ns + "client_name"] = f.get("client_name", "")
        st.session_state[ns + "selected_plan"] = f.get("selected_plan", "")
        st.session_state[ns + "start"] = _parse(f.get("start_date")) or date.today()
        st.session_state[ns + "exp"] = _parse(f.get("current_exp")) or date.today()
        st.session_state[ns + "exp_touched"] = True
        st.session_state[ns + "months"] = int(f.get("ext_months") or 6)
    else:
        for tok, val in f.items():
            st.session_state[ns + tok] = _parse(val)
    for tok, val in ex.items():
        st.session_state[ns + "x_" + tok] = _parse(val)


def duplicate_type(src):
    n = len(D()["custom_types"]) + 1
    key = f"custom{n}"
    while any(c["key"] == key for c in D()["custom_types"]) or key in BUILTINS:
        n += 1; key = f"custom{n}"
    D()["custom_types"].append({"key": key, "name": type_name(src["key"]) + " (копия)",
                                "var_tokens": list(all_tokens(src))})
    D()["texts"][key] = text_of(src["key"])
    D().setdefault("type_created", {})[key] = date.today().isoformat()
    return key


# ---------------- меню (тоглы) ----------------
with st.sidebar:
    st.markdown("### Документы")
    q = st.text_input("🔎 Поиск типа", key="type_search", placeholder="название типа…").strip().lower()
    subs = [("create", "создать документ"), ("template", "шаблон"), ("created", "созданные документы")]
    shown = [t for t in all_types() if not q or q in t["name"].lower()]
    if not shown and q:
        st.caption("Ничего не найдено.")
    for t in shown:
        with st.expander(t["name"].upper(), expanded=(st.session_state.type == t["key"])):
            for sk, sl in subs:
                active = st.session_state.type == t["key"] and st.session_state.section == sk
                if st.button(("• " if active else "") + sl, key=f"nav_{t['key']}_{sk}",
                             use_container_width=True):
                    goto(t["key"], sk); st.rerun()
            d1, d2 = st.columns(2)
            if d1.button("📑 Дублировать", key=f"dup_{t['key']}", use_container_width=True):
                nk = duplicate_type(t); save_data(); goto(nk, "template"); st.rerun()
            if d2.button("🗑 В архив", key=f"arch_{t['key']}", use_container_width=True):
                archive_type(t["key"])
                rem = [x["key"] for x in all_types()]
                if st.session_state.type == t["key"]:
                    st.session_state.type = rem[0] if rem else None
                save_data(); st.rerun()
    st.divider()
    if st.button("➕ Создать новый тип", use_container_width=True):
        n = len(D()["custom_types"]) + 1
        key = f"custom{n}"
        while any(c["key"] == key for c in D()["custom_types"]):
            n += 1; key = f"custom{n}"
        D()["custom_types"].append({"key": key, "name": f"Новый тип документа {n}", "var_tokens": ["name"]})
        D()["texts"][key] = "# НОВЫЙ ДОКУМЕНТ\n\nClient: {name}\n\n(добавь поля и текст ниже)"
        D().setdefault("type_created", {})[key] = date.today().isoformat()
        save_data(); goto(key, "template"); st.rerun()

    arch = D().get("archived", {})
    if arch:
        st.divider()
        with st.expander(f"🗄 Архив ({len(arch)})"):
            for key in list(arch.keys()):
                created = fmt_iso(D().get("type_created", {}).get(key, ""))
                deleted = fmt_iso(arch[key])
                st.markdown(f"**{type_name(key)}**  \n<span style='font-size:11px;color:gray'>"
                            f"создан: {created} · удалён: {deleted}</span>", unsafe_allow_html=True)
                if st.button("↩️ Восстановить", key=f"restore_{key}", use_container_width=True):
                    restore_type(key); save_data(); goto(key, "create"); st.rerun()

    st.divider()
    src = st.session_state.get("storage_src", "local")
    label = {"gsheets": "🟢 Google-таблица", "local": "🟡 локально (сбросится при перезапуске)",
             "empty": "🟡 локально"}.get(src, src)
    st.caption(f"Хранение: {label}")

# ---------------- контент ----------------
types_now = all_types()
if st.session_state.type not in [x["key"] for x in types_now]:
    st.session_state.type = types_now[0]["key"] if types_now else None
t = get_type(st.session_state.type)
sec = st.session_state.section
if t is None:
    st.info("Все типы документов в архиве. Восстанови нужный из раздела «Архив» слева.")
    st.stop()

# ===== СОЗДАТЬ =====
if sec == "create":
    st.title(f"{t['name']} — создать")
    if st.session_state.step == 1:
        st.caption("Шаг 1 из 2 — данные")
        form, extra = render_form(t)
        if st.button("Далее — предпросмотр →", type="primary"):
            errs = []
            if t["kind"] in ("freeze", "extension"):
                if not form["client_name"]:
                    errs.append("Имя клиента")
                if not form["selected_plan"]:
                    errs.append("План")
            # обязательные пользовательские/доп. поля
            for tok in all_tokens(t):
                v = var_get(tok)
                if v.get("required") and (tok in form or tok in extra):
                    val = form.get(tok, extra.get(tok))
                    if v["type"] == "text" and not str(val or "").strip():
                        errs.append(v["label"])
            if errs:
                st.error("Заполни обязательные поля: " + ", ".join(errs) + ".")
            else:
                r = compute_full(t, form, extra)
                if r["err"]:
                    st.error(r["err"])
                else:
                    st.session_state.cur_ctx = r["ctx"]
                    sf, se = serialize_form(form, extra)
                    st.session_state.cur_form = sf
                    st.session_state.cur_extra = se
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
        st.markdown(preview_html(text_of(t["key"]), ctx, client, True, highlight_vars=True),
                    unsafe_allow_html=True)
        st.write("")
        docx_bytes = E.build_docx(text_of(t["key"]), ctx, client)
        fname = f"{E.safe_name(client)}_{t['key']}"
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("← Назад", use_container_width=True):
                st.session_state.step = 1; st.rerun()
        with b2:
            st.download_button("⬇️ .docx", docx_bytes, file_name=fname + ".docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True)
        with b3:
            if E._find_soffice():
                try:
                    pdf_bytes = cached_pdf(text_of(t["key"]), json.dumps(ctx, ensure_ascii=False), client)
                    st.download_button("⬇️ PDF", pdf_bytes, file_name=fname + ".pdf",
                        mime="application/pdf", use_container_width=True)
                except Exception:
                    st.caption("PDF —")
            else:
                st.caption("нет PDF")
        with b4:
            if st.button("💾 Сохранить", type="primary", use_container_width=True):
                D()["saved"].setdefault(t["key"], []).insert(0, {
                    "client": client or "—", "date": date.today().strftime(E.DATE_FMT),
                    "created_iso": date.today().isoformat(),
                    "type_name": t["name"], "text": text_of(t["key"]), "ctx": ctx,
                    "form": st.session_state.get("cur_form", {}),
                    "extra": st.session_state.get("cur_extra", {})})
                save_data(); st.success("Сохранено в «созданные документы».")

# ===== ШАБЛОН =====
elif sec == "template":
    st.title(f"{t['name']} — шаблон")
    if not t["builtin"]:
        ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
        ct["name"] = st.text_input("Название типа документа", ct["name"])

    st.markdown("**Текст документа** — таблица подписей добавляется автоматически в конце.")
    ret = template_editor(text=text_of(t["key"]), variables=vars_panel(t),
                          key=f"editor_{t['key']}_{st.session_state.editor_nonce}")
    if isinstance(ret, dict):
        txt = ret.get("text")
        if txt is not None:
            D()["texts"][t["key"]] = txt
        cmd = ret.get("cmd")
        if cmd and cmd.get("id") and cmd.get("id") != st.session_state.get("last_cmd_id"):
            st.session_state["last_cmd_id"] = cmd["id"]
            if cmd.get("action") == "del" and cmd.get("token"):
                remove_token_from_type(t, cmd["token"])
                save_data(); st.rerun()
    elif ret is not None:
        D()["texts"][t["key"]] = ret

    with st.expander("➕ Добавить / создать переменную"):
        cur_toks = all_tokens(t)
        avail = [v for v in variables() if v["token"] not in cur_toks]
        opts = ["➕ Создать новую переменную"] + [f"{v['label']}  ·  {{{v['token']}}}" for v in avail]
        choice = st.selectbox("Переменная", opts, key=f"addsel_{t['key']}")
        if choice == "➕ Создать новую переменную":
            type_labels = [("text", "текст"), ("date", "дата"), ("number", "число"),
                           ("dur_days", "длительность (дни)"), ("dur_months", "длительность (месяцы)"),
                           ("calc_date", "вычисляемая дата (дата + длительность)")]
            nl = st.text_input("Название (метка)", key=f"nl_{t['key']}")
            ntok = st.text_input("Токен (латиницей, без пробелов)", key=f"nt_{t['key']}")
            ntype_label = st.selectbox("Тип", [l for _, l in type_labels], key=f"nty_{t['key']}")
            ntype = dict((l, v) for v, l in type_labels)[ntype_label]
            nreq = st.checkbox("Обязательное поле", key=f"nreq_{t['key']}",
                               help="Нельзя будет создать документ, пока поле не заполнено")
            base = dur = None
            if ntype == "calc_date":
                date_toks = [tok for tok in cur_toks if var_get(tok)["type"] == "date"]
                dur_toks = [tok for tok in cur_toks if var_get(tok)["type"] in ("dur_days", "dur_months")]
                if not date_toks or not dur_toks:
                    st.info("Сначала добавь в этот документ переменную-дату и переменную-длительность, "
                            "потом создавай вычисляемую дату.")
                else:
                    base = st.selectbox("База (дата)",
                        date_toks, format_func=lambda x: f"{var_get(x)['label']}  ·  {{{x}}}",
                        key=f"cb_{t['key']}")
                    dur = st.selectbox("Длительность",
                        dur_toks, format_func=lambda x: f"{var_get(x)['label']}  ·  {{{x}}}",
                        key=f"cd_{t['key']}")
            if st.button("Создать и добавить", key=f"addnew_{t['key']}"):
                tok = "".join(ch for ch in ntok if ch.isalnum() or ch == "_")
                if not tok:
                    st.error("Укажи токен.")
                elif any(v["token"] == tok for v in variables()):
                    st.error("Такой токен уже есть — выбери его из списка.")
                elif ntype == "calc_date" and not (base and dur):
                    st.error("Для вычисляемой даты нужны переменная-дата и переменная-длительность.")
                else:
                    nv = {"token": tok, "label": nl or tok, "type": ntype, "required": bool(nreq)}
                    if ntype == "calc_date":
                        nv["base"] = base; nv["dur"] = dur
                    variables().append(nv)
                    add_token_to_type(t, tok); save_data(); st.rerun()
        else:
            if st.button("Добавить", key=f"addex_{t['key']}"):
                tok = avail[opts.index(choice) - 1]["token"]
                add_token_to_type(t, tok); save_data(); st.rerun()

    with st.expander("🗑 Удалить переменную совсем (из всех документов)"):
        deletable = [v for v in variables() if v["token"] not in DEFAULT_TOKENS]
        if not deletable:
            st.caption("Своих переменных пока нет. Системные переменные удалять нельзя.")
        else:
            labels = [f"{v['label']}  ·  {{{v['token']}}}" for v in deletable]
            dv = st.selectbox("Переменная", labels, key="delsel")
            dtok = deletable[labels.index(dv)]["token"]
            if st.button("Удалить переменную везде", key="delbtn"):
                st.session_state.pending_del_var = dtok
                st.rerun()

    if st.session_state.get("pending_del_var"):
        tok = st.session_state.pending_del_var
        if any(v["token"] == tok for v in variables()):
            usage = variable_usage(tok)
            if usage:
                used = ", ".join(f"«{n}» (×{c} в тексте)" for n, c, _ in usage)
            else:
                used = "нигде"
            st.warning(f"Точно удалить переменную **{{{tok}}}**?\n\n"
                       f"Используется в: {used}.\n\n"
                       f"Она будет удалена из всех документов и убрана из всех текстов. "
                       f"Это действие необратимо.")
            cc = st.columns(2)
            if cc[0].button("Да, удалить везде", type="primary", key="del_yes"):
                delete_variable_everywhere(tok)
                st.session_state.pending_del_var = None
                st.session_state.editor_nonce += 1
                save_data(); st.rerun()
            if cc[1].button("Отмена", key="del_no"):
                st.session_state.pending_del_var = None
                st.rerun()
        else:
            st.session_state.pending_del_var = None

    with st.expander("🔎 Все переменные / обязательность"):
        TYPE_RU = {"text": "текст", "date": "дата", "number": "число",
                   "dur_days": "дни", "dur_months": "месяцы", "calc_date": "вычисл. дата"}
        vq = st.text_input("Поиск переменной", key="varsearch",
                           placeholder="по названию или токену…").strip().lower()
        rows = [v for v in variables()
                if not vq or vq in v["label"].lower() or vq in v["token"].lower()]
        if not rows:
            st.caption("Ничего не найдено.")
        for v in rows:
            c = st.columns([5, 2, 2])
            c[0].markdown(f"`{{{v['token']}}}` — {v['label']}")
            c[1].caption(TYPE_RU.get(v["type"], v["type"]))
            if v["type"] == "text":
                newreq = c[2].checkbox("обяз.", value=bool(v.get("required")),
                                       key=f"req_{v['token']}")
                if newreq != bool(v.get("required")):
                    v["required"] = newreq; save_data(); st.rerun()
            else:
                c[2].caption("—")

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
    ph = {tok: lbl for tok, lbl in vars_panel(t)}
    st.markdown(preview_html(text_of(t["key"]), ph, "Имя клиента", False, highlight_vars=True),
                unsafe_allow_html=True)

# ===== СОЗДАННЫЕ =====
elif sec == "created":
    st.title(f"{t['name']} — созданные документы")
    saved = D()["saved"].get(t["key"], [])
    if not saved:
        st.info("Пока пусто. Создай и сохрани документ.")
    else:
        dq = st.text_input("🔎 Поиск по имени клиента", key=f"docsearch_{t['key']}",
                           placeholder="имя клиента…").strip().lower()
        shown = [(i, e) for i, e in enumerate(saved)
                 if not dq or dq in str(e.get("client", "")).lower()]
        if not shown:
            st.caption("Ничего не найдено.")
        for i, e in shown:
            with st.container(border=True):
                c = st.columns([4, 1, 1, 1, 1])
                c[0].markdown(f"**{e['client']}**  \n<span style='color:gray;font-size:12px'>"
                              f"создан: {e['date']} · {e['type_name']}</span>", unsafe_allow_html=True)
                client = e["ctx"].get("name", e.get("client", ""))
                docx_bytes = E.build_docx(e["text"], e["ctx"], client)
                fname = f"{E.safe_name(e['client'])}_{t['key']}"
                c[1].download_button("⬇️ .docx", docx_bytes, file_name=fname + ".docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"dl_{t['key']}_{i}", use_container_width=True)
                if E._find_soffice():
                    try:
                        pdf_bytes = cached_pdf(e["text"], json.dumps(e["ctx"], ensure_ascii=False), client)
                        c[2].download_button("⬇️ PDF", pdf_bytes, file_name=fname + ".pdf",
                            mime="application/pdf", key=f"dlp_{t['key']}_{i}", use_container_width=True)
                    except Exception:
                        c[2].caption("PDF —")
                if c[3].button("✏️ Изменить", key=f"edit_{t['key']}_{i}", use_container_width=True):
                    repopulate(t, e.get("form", {}), e.get("extra", {}))
                    goto(t["key"], "create")
                    st.session_state.step = 1
                    st.rerun()
                with c[4].popover("🗑", use_container_width=True):
                    st.write("Удалить документ безвозвратно?")
                    if st.button("Да, удалить", key=f"deldoc_{t['key']}_{i}", type="primary"):
                        saved.pop(i); save_data(); st.rerun()
