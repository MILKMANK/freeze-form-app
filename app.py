"""
Go Offer Docs — генератор документов по шаблонам.
Запуск:  streamlit run app.py
"""
import json, string
from datetime import date
from pathlib import Path
from urllib.parse import quote

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
         "type_created": {}, "archived": {}, "required": {}, "deleted_defaults": [], "sig_table": {},
         "filename": {}}
    loaded, src = storage.load(DATA_FILE)
    st.session_state["storage_src"] = src
    if loaded:
        d.update(loaded)
    have = {v["token"] for v in d.get("variables", [])}
    gone = set(d.get("deleted_defaults", []))
    for v in DEFAULT_VARS:
        if v["token"] not in have and v["token"] not in gone:
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
        out.append({"key": ct["key"], "name": ct["name"], "builtin": False,
                    "kind": ct.get("kind", "custom"),
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
def cached_pdf(text, ctx_json, client, with_sig=True):
    ctx = json.loads(ctx_json)
    return E.docx_to_pdf_bytes(E.build_docx(text, ctx, client, with_signature=with_sig))


def sig_enabled(t):
    return D().setdefault("sig_table", {}).get(t["key"], True)


def set_sig(t, val):
    D().setdefault("sig_table", {})[t["key"]] = bool(val)


DEFAULT_FNAME = "{client}_{type}"


def filename_template(t):
    return D().setdefault("filename", {}).get(t["key"], DEFAULT_FNAME)


def set_filename_template(t, val):
    D().setdefault("filename", {})[t["key"]] = val


def build_filename(t, ctx, client):
    tpl = filename_template(t) or DEFAULT_FNAME
    data = {k: ("" if v is None else str(v)) for k, v in (ctx or {}).items()}
    data["client"] = client or data.get("name", "") or "—"
    data["type"] = t["name"]
    data["type_key"] = t["key"]
    data["date"] = date.today().strftime("%Y-%m-%d")
    out = tpl
    for k, v in data.items():
        out = out.replace("{" + k + "}", v)
    # убрать незаполненные {что-то}
    while "{" in out and "}" in out:
        i = out.index("{"); j = out.index("}", i)
        out = out[:i] + out[j + 1:]
    return E.safe_name(out.strip()) or "document"


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
                    "base": v.get("base"), "dur": v.get("dur"),
                    "expr": v.get("expr"), "out": v.get("out"),
                    "default_expr": v.get("default_expr")})
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


def _uses_base_form(t):
    return t["kind"] in ("freeze", "extension")


def add_token_to_type(t, tok):
    if _uses_base_form(t):
        lst = D().setdefault("extra_tokens", {}).setdefault(t["key"], [])
        if tok not in lst and tok not in base_tokens(t):
            lst.append(tok)
    else:
        ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
        ct.setdefault("var_tokens", [])
        if tok not in ct["var_tokens"]:
            ct["var_tokens"].append(tok)


def remove_token_from_type(t, tok):
    """Убирает переменную из набора документа (базовые поля форм не трогаем)."""
    if _uses_base_form(t):
        lst = D().setdefault("extra_tokens", {}).get(t["key"], [])
        if tok in lst:
            lst.remove(tok)
    else:
        ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
        if tok in ct.get("var_tokens", []):
            ct["var_tokens"].remove(tok)


TYPE_RU = {"text": "текст", "date": "дата", "number": "число",
           "dur_days": "длительность (дни)", "dur_months": "длительность (мес.)",
           "calc_date": "вычисляемая дата", "formula": "формула"}


def in_text(t, tok):
    return ("{" + tok + "}") in (text_of(t["key"]) or "")


def required_tokens(t):
    return D().setdefault("required", {}).setdefault(t["key"], [])


def needed_tokens(t):
    """Замыкание переменных, реально нужных для текста: сами токены из текста +
       всё, от чего зависят формулы / вычисляемые даты / значения по умолчанию."""
    txt = text_of(t["key"]) or ""
    valid = {v["token"] for v in variables()}
    needed = set()
    frontier = [v["token"] for v in variables() if ("{" + v["token"] + "}") in txt]
    while frontier:
        tok = frontier.pop()
        if tok in needed or tok not in valid:
            continue
        needed.add(tok)
        v = var_get(tok)
        refs = []
        if v.get("type") == "formula":
            refs += E.refs_in(v.get("expr", ""))
        if v.get("type") == "calc_date":
            refs += [v.get("base"), v.get("dur")]
        if v.get("default_expr"):
            refs += E.refs_in(v.get("default_expr", ""))
        for r in refs:
            if r and r in valid and r not in needed:
                frontier.append(r)
    return needed


def sync_type_with_text(t):
    """Поля типа = ровно замыкание переменных, нужных тексту. Лишние (например,
       оставшиеся после дублирования) убираются. Обязательность чистится по тексту."""
    changed = False
    needed = needed_tokens(t)
    if _uses_base_form(t):
        base = set(base_tokens(t))
        new_extra = [tok for tok in needed if tok not in base]
        cur = D().setdefault("extra_tokens", {}).get(t["key"], [])
        kept = [tok for tok in cur if tok in needed]
        for tok in new_extra:
            if tok not in kept:
                kept.append(tok)
        if kept != cur:
            D()["extra_tokens"][t["key"]] = kept; changed = True
    else:
        ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
        cur = ct.get("var_tokens", [])
        kept = [tok for tok in cur if tok in needed]
        for tok in needed:
            if tok not in kept:
                kept.append(tok)
        if kept != cur:
            ct["var_tokens"] = kept; changed = True
    req = required_tokens(t)
    pruned = [tok for tok in req if in_text(t, tok)]
    if pruned != req:
        req[:] = pruned; changed = True
    return changed


def set_required(t, tok, value):
    req = required_tokens(t)
    if value and in_text(t, tok):
        if tok not in req:
            req.append(tok)
    else:
        if tok in req:
            req.remove(tok)


def editor_vars(t):
    """Все переменные программы для правой панели: [token, label, тип-текст, обязательна?]."""
    req = set(required_tokens(t))
    return [[v["token"], v["label"], TYPE_RU.get(v["type"], v["type"]), v["token"] in req]
            for v in variables()]


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
    # системные токены помечаем удалёнными, чтобы не пересоздавались при загрузке
    dd = D().setdefault("deleted_defaults", [])
    for tk in toks:
        if tk in DEFAULT_TOKENS and tk not in dd:
            dd.append(tk)
    # также убираем из обязательных по типам
    for k in list(D().get("required", {}).keys()):
        D()["required"][k] = [x for x in D()["required"][k] if x not in toks]


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


def _value_key(t, ns, tok):
    """Ключ session_state для значения переменной с учётом типа формы."""
    if _uses_base_form(t):
        bmap = {"name": "client_name", "plan": "selected_plan", "start_date": "start",
                "orig_expiration": "exp", "current_expiration": "exp", "break_start": "bstart",
                "break_days": "bdays", "break_end": "bend", "extension_months": "months",
                "reason": "reason", "exhibit": "exhibit"}
        return ns + bmap.get(tok, "x_" + tok)
    return ns + tok


def compute_default(t, expr, ns, out_type):
    """Значение по умолчанию из формулы, опираясь на текущие значения других полей."""
    try:
        env = {}
        for ref in E.refs_in(expr):
            v = st.session_state.get(_value_key(t, ns, ref))
            vt = var_get(ref).get("type")
            if isinstance(v, date):
                env[ref] = float(v.toordinal())
            elif isinstance(v, bool):
                env[ref] = float(v)
            elif isinstance(v, (int, float)):
                env[ref] = float(v)
            elif v in (None, ""):
                env[ref] = 0.0 if vt in ("number", "dur_days", "dur_months") else None
            else:
                env[ref] = str(v)
        val = E.evaluate_formula(expr, env)
        if out_type == "date":
            return date.fromordinal(int(round(float(val))))
        return int(round(float(val)))
    except Exception:
        return date.today() if out_type == "date" else 0


def _render_extra(t, ns):
    extra = {}
    toks = [tk for tk in extra_tokens(t)]
    inputs = [tk for tk in toks if var_get(tk)["type"] not in ("calc_date", "formula")]
    if inputs:
        st.markdown("**Дополнительные поля**")

    # сначала пересчитываем поля с формулой-умолчанием в порядке зависимостей (итеративно)
    defx_fields = [tk for tk in inputs if var_get(tk).get("default_expr")]
    for _it in range(len(defx_fields) + 2):
        any_change = False
        for tok in defx_fields:
            key = ns + "x_" + tok; tk = key + "_touched"
            if st.session_state.get(tk):
                continue
            v = var_get(tok)
            ot = "date" if v["type"] == "date" else "number"
            dflt = compute_default(t, v["default_expr"], ns, ot)
            if st.session_state.get(key) != dflt:
                st.session_state[key] = dflt; any_change = True
            _ensure(tk, False)
        if not any_change:
            break

    def _render(tok):
        v = var_get(tok); tp = v["type"]; key = ns + "x_" + tok
        dx = v.get("default_expr")
        if tp == "date":
            if dx:
                tk = key + "_touched"
                extra[tok] = st.date_input(v["label"], key=key, on_change=_mark, args=(tk,))
            else:
                _ensure(key, date.today())
                extra[tok] = st.date_input(v["label"], key=key)
        elif tp in ("number", "dur_days", "dur_months"):
            lbl = v["label"] + (" (дней)" if tp == "dur_days" else " (мес.)" if tp == "dur_months" else "")
            if dx:
                tk = key + "_touched"
                extra[tok] = st.number_input(lbl, step=1, key=key, on_change=_mark, args=(tk,))
            else:
                extra[tok] = st.number_input(lbl, value=None, step=1, key=key,
                                             placeholder="число (пусто = 0)")
        else:
            extra[tok] = st.text_input(v["label"], key=key)

    for tok in inputs:
        _render(tok)
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
            if "orig_expiration" in D().get("deleted_defaults", []):
                orig_exp = E.add_months(st.session_state[ns + "start"], 6)
            else:
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
            if "current_expiration" in D().get("deleted_defaults", []):
                cur = E.add_months(st.session_state[ns + "start"], 6)
            else:
                cur = linked_expiration(ns, ns + "start", "Текущая дата окончания (по умолч. +6 мес.)")
            if "extension_months" in D().get("deleted_defaults", []):
                ext_months = 0
            else:
                st.subheader("Параметры продления")
                st.number_input("Продлить на (месяцев)", 1, 120, 6, 1, key=ns + "months")
                ext_months = st.session_state[ns + "months"]
            form = {"exhibit": st.session_state[ns + "exhibit"],
                    "client_name": st.session_state[ns + "client_name"].strip(),
                    "selected_plan": st.session_state[ns + "selected_plan"].strip(),
                    "start_date": st.session_state[ns + "start"], "current_exp": cur,
                    "ext_months": ext_months}
            return form, _render_extra(t, ns)
    else:
        form = {}
        flds = fields_of(t)
        inputs = [f for f in flds if f["type"] not in ("calc_date", "formula")]
        if not inputs:
            st.info("У этого типа пока нет полей для ввода. Добавь их в разделе «шаблон».")

        def _render_field(f):
            tp = f["type"]; key = ns + f["key"]
            dx = f.get("default_expr")
            if tp == "date":
                if dx:
                    tk = key + "_touched"
                    form[f["key"]] = st.date_input(f["label"], key=key, on_change=_mark, args=(tk,))
                else:
                    _ensure(key, date.today())
                    form[f["key"]] = st.date_input(f["label"], key=key)
            elif tp in ("number", "dur_days", "dur_months"):
                lbl = f["label"] + (" (дней)" if tp == "dur_days" else " (мес.)" if tp == "dur_months" else "")
                if dx:
                    tk = key + "_touched"
                    form[f["key"]] = st.number_input(lbl, step=1, key=key, on_change=_mark, args=(tk,))
                else:
                    form[f["key"]] = st.number_input(lbl, value=None, step=1, key=key,
                                                     placeholder="число (пусто = 0)")
            else:
                form[f["key"]] = st.text_input(f["label"], key=key)

        # пересчёт полей с формулой-умолчанием в порядке зависимостей (итеративно)
        defx = [f for f in inputs if f.get("default_expr")]
        for _it in range(len(defx) + 2):
            any_change = False
            for f in defx:
                key = ns + f["key"]; tk = key + "_touched"
                if st.session_state.get(tk):
                    continue
                ot = "date" if f["type"] == "date" else "number"
                dflt = compute_default(t, f["default_expr"], ns, ot)
                if st.session_state.get(key) != dflt:
                    st.session_state[key] = dflt; any_change = True
                _ensure(tk, False)
            if not any_change:
                break

        for f in inputs:
            _render_field(f)
        return form, {}


def compute_full(t, form, extra):
    r = compute(t, form)
    if r["err"]:
        return r
    ctx = dict(r["ctx"]); raw = dict(r.get("raw", {}))
    env = {}; vtypes = {}
    for tok, val in raw.items():  # встроенные базовые значения -> серийные даты/числа
        vtypes[tok] = var_get(tok)["type"]
        if isinstance(val, date):
            env[tok] = float(val.toordinal())
        elif isinstance(val, bool):
            env[tok] = float(val)
        elif isinstance(val, (int, float)):
            env[tok] = float(val)
        else:
            env[tok] = val
    derived = []
    for tok in extra_tokens(t):
        v = var_get(tok); vtypes[tok] = v["type"]
        if v["type"] in ("formula", "calc_date"):
            derived.append(v); continue
        val = extra.get(tok)
        if v["type"] == "date":
            env[tok] = val.toordinal() if val else None
            ctx[tok] = E.fmt(val) if val else "—"
        elif v["type"] in ("number", "dur_days", "dur_months"):
            n = 0 if val in (None, "") else int(val)
            env[tok] = float(n); ctx[tok] = str(n)
        else:
            env[tok] = "" if val in (None, "") else str(val); ctx[tok] = env[tok]
    ctx.update(E.resolve_derived(derived, env, vtypes))
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
             ("last_cmd_id", None), ("pending_del_var", None),
             ("admin_ok", False), ("admin_pending", None)]:
    if k not in st.session_state:
        st.session_state[k] = v


def _edit_pw():
    try:
        return st.secrets.get("edit_password", None)
    except Exception:
        return None


def admin_unlocked():
    return (_edit_pw() is None) or st.session_state.get("admin_ok", False)


def request_admin(action, key=None):
    """Если разблокировано — вернёт True (действие выполнять сразу). Иначе запросит пароль."""
    if admin_unlocked():
        return True
    st.session_state.admin_pending = {"act": action, "key": key}
    st.rerun()


def _slug(s):
    return "".join(ch if ch.isalnum() else "_" for ch in str(s).lower())


APP_URL = "https://freeze-form-app.streamlit.app/"


def prefill_tokens(t):
    """Входные переменные типа (которые можно передать в ссылке)."""
    if t["kind"] == "freeze":
        base = ["name", "plan", "exhibit", "start_date", "orig_expiration",
                "break_start", "break_end", "break_days", "reason"]
    elif t["kind"] == "extension":
        base = ["name", "plan", "exhibit", "start_date", "current_expiration", "extension_months"]
    else:
        base = []
    toks = list(base)
    src = extra_tokens(t) if _uses_base_form(t) else t["var_tokens"]
    for tok in src:
        if var_get(tok)["type"] not in ("formula", "calc_date") and tok not in toks:
            toks.append(tok)
    return toks


def prefill_link(t):
    parts = ["type=" + t["key"]]
    for tok in prefill_tokens(t):
        parts.append(tok + "=" + var_get(tok)["label"])
    return APP_URL + "?" + "&".join(parts)


def resolve_type_key(v):
    v = (v or "").strip()
    vs = _slug(v)
    for t in all_types():
        if t["key"].lower() == v.lower():
            return t["key"]
    for t in all_types():
        if _slug(t["name"]) == vs:
            return t["key"]
    for t in all_types():
        ns = _slug(t["name"])
        if vs and (vs in ns or ns in vs):
            return t["key"]
    return None


def _conv_param(val, vtype):
    s = str(val)
    if vtype == "date":
        from datetime import datetime
        for f in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, f).date()
            except Exception:
                pass
        return None
    if vtype in ("number", "dur_days", "dur_months"):
        try:
            return int(float(s))
        except Exception:
            return None
    return s


_TYPE_PARAMS = ("type", "form", "doc", "документ")


def apply_prefill():
    if st.session_state.get("_prefilled"):
        return
    try:
        params = st.query_params
        keys = list(params.keys())
    except Exception:
        st.session_state["_prefilled"] = True
        return
    if not keys:
        st.session_state["_prefilled"] = True
        return
    tkey = None
    for pk in _TYPE_PARAMS:
        if pk in keys:
            tkey = resolve_type_key(params.get(pk))
            if tkey:
                break
    if tkey:
        st.session_state.type = tkey
        st.session_state.section = "create"
        st.session_state.step = 1
    t = get_type(tkey or st.session_state.type)
    if t:
        ns = t["key"] + "_"
        bmap = {}
        if t["kind"] == "freeze":
            bmap = {"name": "client_name", "plan": "selected_plan", "start_date": "start",
                    "orig_expiration": "exp", "break_start": "bstart", "break_days": "bdays",
                    "break_end": "bend", "reason": "reason", "exhibit": "exhibit"}
        elif t["kind"] == "extension":
            bmap = {"name": "client_name", "plan": "selected_plan", "start_date": "start",
                    "current_expiration": "exp", "extension_months": "months", "exhibit": "exhibit"}
        for tok in keys:
            if tok in _TYPE_PARAMS:
                continue
            v = var_get(tok)
            val = _conv_param(params.get(tok), v["type"])
            if val is None:
                continue
            if t["kind"] in ("freeze", "extension"):
                if tok in bmap:
                    st.session_state[ns + bmap[tok]] = val
                    if tok in ("orig_expiration", "current_expiration"):
                        st.session_state[ns + "exp_touched"] = True
                    if tok == "break_end":
                        st.session_state[ns + "mode"] = "По дате окончания"
                    if tok == "break_days":
                        st.session_state[ns + "mode"] = "По количеству дней"
                else:
                    st.session_state[ns + "x_" + tok] = val
            else:
                st.session_state[ns + tok] = val
                if v.get("default_expr"):
                    st.session_state[ns + tok + "_touched"] = True
    st.session_state["_prefilled"] = True


apply_prefill()


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


def _date_from_fmt(s):
    from datetime import datetime
    try:
        return datetime.strptime(str(s), E.DATE_FMT).date().isoformat()
    except Exception:
        return None


def _num_or(s, default):
    try:
        return int(float(str(s)))
    except Exception:
        return default


def _form_from_ctx(t, ctx):
    """Восстановить (form, extra) из готовых значений документа (для старых записей)."""
    ctx = ctx or {}
    extra = {}
    for tok in extra_tokens(t):
        v = var_get(tok)
        if v["type"] == "calc_date":
            continue
        val = ctx.get(tok, "")
        if v["type"] == "date":
            extra[tok] = _date_from_fmt(val)
        elif v["type"] in ("number", "dur_days", "dur_months"):
            extra[tok] = _num_or(val, 0)
        else:
            extra[tok] = val
    if t["kind"] == "freeze":
        bd = _num_or(ctx.get("break_days"), 14)
        form = {"exhibit": ctx.get("exhibit", "A"), "client_name": ctx.get("name", ""),
                "selected_plan": ctx.get("plan", ""),
                "start_date": _date_from_fmt(ctx.get("start_date")),
                "orig_exp": _date_from_fmt(ctx.get("orig_expiration")),
                "break_start": _date_from_fmt(ctx.get("break_start")),
                "mode": "days", "break_days": bd, "break_end": None,
                "reason": "" if ctx.get("reason") in (None, "N/A") else ctx.get("reason", "")}
        return form, extra
    if t["kind"] == "extension":
        form = {"exhibit": ctx.get("exhibit", "A"), "client_name": ctx.get("name", ""),
                "selected_plan": ctx.get("plan", ""),
                "start_date": _date_from_fmt(ctx.get("start_date")),
                "current_exp": _date_from_fmt(ctx.get("current_expiration")),
                "ext_months": _num_or(ctx.get("extension_months"), 6)}
        return form, extra
    form = {}
    for tok in t["var_tokens"]:
        v = var_get(tok)
        if v["type"] == "calc_date":
            continue
        val = ctx.get(tok, "")
        if v["type"] == "date":
            form[tok] = _date_from_fmt(val)
        elif v["type"] in ("number", "dur_days", "dur_months"):
            form[tok] = _num_or(val, 0)
        else:
            form[tok] = val
    return form, {}


def repopulate(t, form, extra, ctx=None):
    """Загружает сохранённые данные документа обратно в форму создания."""
    if not form and ctx:
        form, extra = _form_from_ctx(t, ctx)
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
                                "kind": src["kind"], "var_tokens": list(all_tokens(src))})
    D()["texts"][key] = text_of(src["key"])
    D().setdefault("type_created", {})[key] = date.today().isoformat()
    # копируем доп. поля (для freeze/extension-копий)
    src_extra = list(D().get("extra_tokens", {}).get(src["key"], []))
    if src_extra:
        D().setdefault("extra_tokens", {})[key] = src_extra
    return key


# ---------------- меню (тоглы) ----------------
with st.sidebar:
    st.markdown("### Документы")
    q = st.text_input("🔎 Поиск типа", key="type_search", placeholder="название типа…").strip().lower()
    subs = [("create", "создать документ"), ("created", "созданные документы")]
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
            lk = "" if admin_unlocked() else " 🔒"
            i1, i2, i3 = st.columns([2, 1, 1])
            if i1.button("✏️ шаблон" + lk, key=f"nav_{t['key']}_template", use_container_width=True):
                if request_admin("template", t["key"]):
                    goto(t["key"], "template"); st.rerun()
            if i2.button("📑", key=f"dup_{t['key']}", help="Дублировать", use_container_width=True):
                if request_admin("dup", t["key"]):
                    nk = duplicate_type(t); save_data(); goto(nk, "template"); st.rerun()
            if i3.button("🗄", key=f"arch_{t['key']}", help="В архив", use_container_width=True):
                if request_admin("arch", t["key"]):
                    archive_type(t["key"])
                    rem = [x["key"] for x in all_types()]
                    if st.session_state.type == t["key"]:
                        st.session_state.type = rem[0] if rem else None
                    save_data(); st.rerun()
    st.divider()
    if st.button("➕ Создать новый тип" + ("" if admin_unlocked() else " 🔒"), use_container_width=True):
        if request_admin("newtype", None):
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
                if st.button("↩️ Восстановить" + ("" if admin_unlocked() else " 🔒"),
                             key=f"restore_{key}", use_container_width=True):
                    if request_admin("restore", key):
                        restore_type(key); save_data(); goto(key, "create"); st.rerun()

    st.divider()
    if _edit_pw() is not None:
        if st.session_state.get("admin_ok"):
            st.caption("🔓 Редактирование разблокировано")
            if st.button("Заблокировать редактирование", use_container_width=True):
                st.session_state.admin_ok = False
                if st.session_state.section == "template":
                    goto(st.session_state.type, "create")
                st.rerun()
        else:
            st.caption("🔒 Редактирование защищено паролем")
    src = st.session_state.get("storage_src", "local")
    label = {"gsheets": "🟢 Google-таблица", "local": "🟡 локально (сбросится при перезапуске)",
             "empty": "🟡 локально"}.get(src, src)
    st.caption(f"Хранение: {label}")
    if storage.gdrive_configured():
        st.caption("📁 Созданные файлы выгружаются в Google Drive")
    if src != "gsheets":
        st.caption("⚠️ Данные не сохраняются между перезапусками. Подключи Google-таблицу, "
                   "чтобы шаблоны не пропадали.")
        if storage.gsheets_configured():
            with st.expander("🔌 Проверить подключение к Google"):
                if st.button("Проверить сейчас", use_container_width=True, key="gcheck"):
                    ok_s, msg_s = storage.check_gsheets()
                    (st.success if ok_s else st.error)(f"Таблица: {msg_s}")
                    if storage.gdrive_configured():
                        ok_d, msg_d = storage.check_gdrive()
                        (st.success if ok_d else st.error)(f"Drive: {msg_d}")
                    if ok_s:
                        st.info("Подключение есть. Нажми «Reboot app», чтобы переключиться на 🟢.")
    if admin_unlocked():
        with st.expander("💾 Резервная копия", expanded=False):
            st.download_button("⬇️ Скачать копию (.json)",
                               json.dumps(D(), ensure_ascii=False, indent=2),
                               file_name="go-offer-backup.json", mime="application/json",
                               use_container_width=True)
            # сохранить копию в папку Google Drive
            def _bk_folder():
                d = D().get("backup_folder")
                if d:
                    return d
                try:
                    return st.secrets["gdrive"].get("backup_folder") or st.secrets["gdrive"].get("folder")
                except Exception:
                    return ""
            bf = st.text_input("Папка Google Drive для бэкапов (ID)", value=_bk_folder() or "",
                               key="bk_folder", placeholder="ID папки из ссылки drive")
            if bf != D().get("backup_folder", ""):
                D()["backup_folder"] = bf; save_data()
            if st.button("☁️ Сохранить копию в Google Drive", use_container_width=True, key="bk_drive"):
                if not bf:
                    st.error("Укажи ID папки для бэкапов.")
                else:
                    try:
                        link = storage.upload_to_drive(
                            f"backup-{date.today().isoformat()}.json",
                            json.dumps(D(), ensure_ascii=False, indent=2).encode("utf-8"),
                            "application/json", folder_id=bf)
                        D()["last_backup"] = date.today().isoformat(); save_data()
                        st.success("Копия сохранена в Google Drive.")
                        if link:
                            st.markdown(f"[Открыть копию]({link})")
                    except Exception as e:
                        st.error(f"Не удалось сохранить в Drive: {e}")
            if D().get("last_backup"):
                st.caption(f"Последняя копия в Drive: {fmt_iso(D()['last_backup'])}")
            up = st.file_uploader("Восстановить из копии (.json)", type=["json"], key="bk_up")
            if up is not None and st.button("Загрузить эту копию", use_container_width=True, key="bk_load"):
                try:
                    st.session_state.data = json.loads(up.getvalue().decode("utf-8"))
                    save_data(); st.success("Восстановлено из копии."); st.rerun()
                except Exception as e:
                    st.error(f"Не удалось прочитать файл: {e}")
            st.caption("Восстановление заменяет все текущие данные данными из файла.")
    else:
        st.caption("🔒 Резервная копия — после ввода пароля редактирования.")

# ---------------- контент ----------------
types_now = all_types()
if st.session_state.type not in [x["key"] for x in types_now]:
    st.session_state.type = types_now[0]["key"] if types_now else None
t = get_type(st.session_state.type)
sec = st.session_state.section
if t is None:
    st.info("Все типы документов в архиве. Восстанови нужный из раздела «Архив» слева.")
    st.stop()

if sync_type_with_text(t):
    save_data(); st.rerun()

# ---------------- админ-гейт (редактирование) ----------------
_pend = st.session_state.get("admin_pending")
if _pend and not admin_unlocked():
    st.title("🔒 Режим редактирования")
    st.caption("Изменение шаблонов, переменных и типов документов защищено паролем администратора. "
               "Создавать документы можно без пароля.")
    pwv = st.text_input("Пароль редактирования", type="password", key="adm_pw_input")
    g1, g2 = st.columns([1, 3])
    if g1.button("Войти", type="primary"):
        if pwv == _edit_pw():
            st.session_state.admin_ok = True; st.rerun()
        else:
            st.error("Неверный пароль.")
    if g2.button("Отмена"):
        st.session_state.admin_pending = None
        goto(st.session_state.type, "create"); st.rerun()
    st.stop()
if _pend and admin_unlocked():
    _act = _pend.get("act"); _key = _pend.get("key")
    st.session_state.admin_pending = None
    if _act == "template":
        goto(_key, "template")
    elif _act == "dup":
        src = get_type(_key)
        if src:
            nk = duplicate_type(src); save_data(); goto(nk, "template")
    elif _act == "arch":
        archive_type(_key)
        rem = [x["key"] for x in all_types()]
        if st.session_state.type == _key:
            st.session_state.type = rem[0] if rem else None
        save_data()
    elif _act == "newtype":
        n = len(D()["custom_types"]) + 1; nkey = f"custom{n}"
        while any(c["key"] == nkey for c in D()["custom_types"]):
            n += 1; nkey = f"custom{n}"
        D()["custom_types"].append({"key": nkey, "name": f"Новый тип документа {n}", "var_tokens": ["name"]})
        D()["texts"][nkey] = "# НОВЫЙ ДОКУМЕНТ\n\nClient: {name}\n\n(добавь поля и текст ниже)"
        D().setdefault("type_created", {})[nkey] = date.today().isoformat()
        save_data(); goto(nkey, "template")
    elif _act == "restore":
        restore_type(_key); save_data(); goto(_key, "create")
    st.rerun()

if sec == "template" and not admin_unlocked():
    request_admin("template", t["key"])

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
            base_map = {"name": "client_name", "plan": "selected_plan",
                        "orig_expiration": "orig_exp", "current_expiration": "current_exp",
                        "extension_months": "ext_months"}
            for tok in required_tokens(t):
                v = var_get(tok)
                ty = v["type"]
                if ty in ("date", "calc_date", "formula"):
                    continue
                if tok in extra:
                    val = extra.get(tok)
                elif tok in form:
                    val = form.get(tok)
                else:
                    val = form.get(base_map.get(tok, tok))
                empty = (val is None) or (ty == "text" and not str(val).strip())
                if empty and v["label"] not in errs:
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
        sig = sig_enabled(t)
        st.markdown(preview_html(text_of(t["key"]), ctx, client, sig, highlight_vars=True),
                    unsafe_allow_html=True)
        st.write("")
        docx_bytes = E.build_docx(text_of(t["key"]), ctx, client, with_signature=sig)
        fname = build_filename(t, ctx, client)
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
                    pdf_bytes = cached_pdf(text_of(t["key"]), json.dumps(ctx, ensure_ascii=False), client, sig)
                    st.download_button("⬇️ PDF", pdf_bytes, file_name=fname + ".pdf",
                        mime="application/pdf", use_container_width=True)
                except Exception:
                    st.caption("PDF —")
            else:
                st.caption("нет PDF")
        with b4:
            if st.button("💾 Сохранить", type="primary", use_container_width=True):
                entry = {
                    "client": client or "—", "date": date.today().strftime(E.DATE_FMT),
                    "created_iso": date.today().isoformat(),
                    "type_name": t["name"], "text": text_of(t["key"]), "ctx": ctx,
                    "sig": sig,
                    "form": st.session_state.get("cur_form", {}),
                    "extra": st.session_state.get("cur_extra", {})}
                if storage.gdrive_configured():
                    try:
                        link = storage.upload_to_drive(
                            fname + ".docx", docx_bytes,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                        entry["drive_docx"] = link
                        if E._find_soffice():
                            try:
                                pdfb = cached_pdf(text_of(t["key"]),
                                                  json.dumps(ctx, ensure_ascii=False), client, sig)
                                entry["drive_pdf"] = storage.upload_to_drive(
                                    fname + ".pdf", pdfb, "application/pdf")
                            except Exception:
                                pass
                        st.success("Сохранено и выгружено в Google Drive.")
                        if link:
                            st.markdown(f"[Открыть документ в Google Drive]({link})")
                    except Exception as e:
                        st.success("Сохранено в «созданные документы».")
                        st.warning(f"Не удалось выгрузить в Google Drive: {e}")
                else:
                    st.success("Сохранено в «созданные документы».")
                D()["saved"].setdefault(t["key"], []).insert(0, entry)
                save_data()

# ===== ШАБЛОН =====
elif sec == "template":
    st.title(f"{t['name']} — шаблон")
    if not t["builtin"]:
        ct = next(c for c in D()["custom_types"] if c["key"] == t["key"])
        ct["name"] = st.text_input("Название типа документа", ct["name"])

    cur_fn = filename_template(t)
    new_fn = st.text_input("Шаблон имени файла", value=cur_fn, key=f"fn_{t['key']}",
                           placeholder=DEFAULT_FNAME)
    if new_fn != cur_fn:
        set_filename_template(t, new_fn); save_data()
    avail = ", ".join("{" + tok + "}" for tok in (["client", "date", "type"] +
                      [v["token"] for v in variables() if in_text(t, v["token"])]))
    st.caption(f"Доступно: {avail}. Пример: {build_filename(t, {}, 'Иван Иванов')}.docx")
    cur_sig = sig_enabled(t)
    new_sig = st.checkbox("Добавлять таблицу подписей в конце документа", value=cur_sig,
                          key=f"sig_{t['key']}")
    if new_sig != cur_sig:
        set_sig(t, new_sig); save_data(); st.rerun()
    st.markdown("**Текст документа**" + (" — таблица подписей добавляется автоматически в конце."
                if new_sig else " — таблица подписей отключена."))
    ret = template_editor(text=text_of(t["key"]), variables=editor_vars(t),
                          key=f"editor_{t['key']}_{st.session_state.editor_nonce}")
    if isinstance(ret, dict):
        txt = ret.get("text")
        if txt is not None:
            D()["texts"][t["key"]] = txt
        cmd = ret.get("cmd")
        if cmd and cmd.get("id") and cmd.get("id") != st.session_state.get("last_cmd_id"):
            st.session_state["last_cmd_id"] = cmd["id"]
            act = cmd.get("action"); tok = cmd.get("token")
            if act == "del" and tok:
                remove_token_from_type(t, tok)
                if tok in required_tokens(t):
                    required_tokens(t).remove(tok)
                save_data(); st.rerun()
            elif act == "req" and tok:
                set_required(t, tok, bool(cmd.get("value")))
                save_data(); st.rerun()
    elif ret is not None:
        D()["texts"][t["key"]] = ret

    with st.expander("🔗 Ссылка для предзаполнения формы"):
        st.caption("Скопируй ссылку и замени метки после «=» на реальные значения "
                   "(даты — в формате ГГГГ-ММ-ДД, пробелы кодируются как %20). "
                   "Переход по ссылке откроет «создать документ» с заполненными полями.")
        st.code(prefill_link(t), language=None)

    with st.expander("➕ Создать новую переменную"):
        st.caption("Создай переменную — затем кликни её в списке справа, чтобы вставить в текст.")
        type_labels = [("text", "текст"), ("date", "дата"), ("number", "число"),
                       ("dur_days", "длительность (дни)"), ("dur_months", "длительность (месяцы)"),
                       ("formula", "формула (Excel-подобная)"),
                       ("calc_date", "вычисляемая дата (дата + длительность)")]
        nl = st.text_input("Название (метка)", key=f"nl_{t['key']}")
        ntok = st.text_input("Токен (латиницей, без пробелов)", key=f"nt_{t['key']}")
        ntype_label = st.selectbox("Тип", [l for _, l in type_labels], key=f"nty_{t['key']}")
        ntype = dict((l, v) for v, l in type_labels)[ntype_label]
        base = dur = None
        fexpr = fout = None
        if ntype == "formula":
            fout_label = st.selectbox("Тип результата", ["дата", "число", "текст"], key=f"fo_{t['key']}")
            fout = {"дата": "date", "число": "number", "текст": "text"}[fout_label]
            fexpr = st.text_area("Формула", key=f"fe_{t['key']}",
                                 placeholder="напр. EDATE({current_expiration}; {extension_months})")
            with st.popover("Переменные и функции"):
                st.caption("Доступные переменные (копируй в формулу):")
                st.code("  ".join("{" + v["token"] + "}" for v in variables()) or "—")
                st.caption("Функции: EDATE(дата; мес.), TODAY(), DATE(г;м;д), DAYS(кон;нач), "
                           "ADDDAYS(дата;дни), YEAR/MONTH/DAY(дата), ROUND/ROUNDUP/ROUNDDOWN(x;знаки), "
                           "INT, ABS, MIN, MAX, SUM, IF(усл;да;нет), AND/OR/NOT, "
                           "UPPER/LOWER/LEN/CONCAT, TEXT(знач;\"DD.MM.YYYY\"), & — склейка, % — процент. "
                           "Даты: дата+дни=дата, дата−дата=дни.")
            if fexpr and fexpr.strip():
                try:
                    test_env = {v["token"]: (float(date.today().toordinal()) if v["type"] in ("date", "calc_date", "formula")
                                             else 1.0 if v["type"] in ("number", "dur_days", "dur_months")
                                             else "текст") for v in variables()}
                    E.evaluate_formula(fexpr, test_env)
                    st.caption("✅ Формула разобрана без ошибок.")
                except Exception as ex:
                    st.warning(f"Проверь формулу: {ex}")
        elif ntype == "calc_date":
            date_toks = [v["token"] for v in variables() if v["type"] == "date"]
            dur_toks = [v["token"] for v in variables() if v["type"] in ("dur_days", "dur_months")]
            if not date_toks or not dur_toks:
                st.info("Сначала создай переменную-дату и переменную-длительность, потом — вычисляемую дату.")
            else:
                base = st.selectbox("База (дата)", date_toks,
                    format_func=lambda x: f"{var_get(x)['label']}  ·  {{{x}}}", key=f"cb_{t['key']}")
                dur = st.selectbox("Длительность", dur_toks,
                    format_func=lambda x: f"{var_get(x)['label']}  ·  {{{x}}}", key=f"cd_{t['key']}")
        defx = ""
        if ntype in ("date", "number", "dur_days", "dur_months"):
            defx = st.text_input("Значение по умолчанию — формула (необязательно, поле останется редактируемым)",
                                 key=f"dx_{t['key']}",
                                 placeholder="напр. EDATE({start_date}; 6) — дата = старт + 6 мес.")
            if defx and defx.strip():
                try:
                    tenv = {v["token"]: (float(date.today().toordinal()) if v["type"] in ("date", "calc_date", "formula")
                                         else 1.0 if v["type"] in ("number", "dur_days", "dur_months")
                                         else "текст") for v in variables()}
                    E.evaluate_formula(defx, tenv)
                    st.caption("✅ Формула значения по умолчанию разобрана без ошибок.")
                except Exception as ex:
                    st.warning(f"Проверь формулу по умолчанию: {ex}")
        if st.button("Создать переменную", key=f"addnew_{t['key']}"):
            tok = "".join(ch for ch in ntok if ch.isalnum() or ch == "_")
            if not tok:
                st.error("Укажи токен.")
            elif any(v["token"] == tok for v in variables()):
                st.error("Такой токен уже есть.")
            elif ntype == "calc_date" and not (base and dur):
                st.error("Для вычисляемой даты нужны переменная-дата и переменная-длительность.")
            elif ntype == "formula" and not (fexpr and fexpr.strip()):
                st.error("Введи формулу.")
            else:
                nv = {"token": tok, "label": nl or tok, "type": ntype}
                if ntype == "calc_date":
                    nv["base"] = base; nv["dur"] = dur
                elif ntype == "formula":
                    nv["expr"] = fexpr.strip(); nv["out"] = fout
                if defx and defx.strip() and ntype in ("date", "number", "dur_days", "dur_months"):
                    nv["default_expr"] = defx.strip()
                variables().append(nv); save_data(); st.rerun()

    with st.expander("✏️ Редактировать переменную"):
        evs = list(variables())
        if not evs:
            st.caption("Переменных пока нет.")
        else:
            elabels = [f"{v['label']}  ·  {{{v['token']}}}  ·  {TYPE_RU.get(v['type'], v['type'])}" for v in evs]
            esel = st.selectbox("Какую переменную", elabels, key="editsel")
            ev = evs[elabels.index(esel)]
            ekey = ev["token"]
            new_label = st.text_input("Название (метка)", value=ev["label"], key=f"el_{ekey}")
            st.caption(f"Тип: {TYPE_RU.get(ev['type'], ev['type'])}. "
                       f"Сам тип сменить нельзя — для этого удали переменную и создай заново.")
            new_expr = ev.get("expr"); new_out = ev.get("out"); new_def = ev.get("default_expr", "")
            if ev["type"] == "formula":
                outs = ["date", "number", "text"]; outl = ["дата", "число", "текст"]
                noi = st.selectbox("Тип результата", outl,
                                   index=outs.index(ev.get("out", "number")), key=f"eo_{ekey}")
                new_out = {"дата": "date", "число": "number", "текст": "text"}[noi]
                new_expr = st.text_area("Формула", value=ev.get("expr", ""), key=f"ee_{ekey}")
                if new_expr and new_expr.strip():
                    try:
                        tenv = {v["token"]: (float(date.today().toordinal()) if v["type"] in ("date", "calc_date", "formula")
                                             else 1.0 if v["type"] in ("number", "dur_days", "dur_months") else "текст")
                                for v in variables()}
                        E.evaluate_formula(new_expr, tenv)
                        st.caption("✅ Формула разобрана без ошибок.")
                    except Exception as ex:
                        st.warning(f"Проверь формулу: {ex}")
            elif ev["type"] in ("date", "number", "dur_days", "dur_months"):
                new_def = st.text_input("Значение по умолчанию — формула (необязательно, поле останется редактируемым)",
                                        value=ev.get("default_expr", ""), key=f"ed_{ekey}",
                                        placeholder="напр. EDATE({start_date}; 6)")
                if new_def and new_def.strip():
                    try:
                        tenv = {v["token"]: (float(date.today().toordinal()) if v["type"] in ("date", "calc_date", "formula")
                                             else 1.0 if v["type"] in ("number", "dur_days", "dur_months") else "текст")
                                for v in variables()}
                        E.evaluate_formula(new_def, tenv)
                        st.caption("✅ Формула по умолчанию разобрана без ошибок.")
                    except Exception as ex:
                        st.warning(f"Проверь формулу: {ex}")
            if st.button("💾 Сохранить изменения", key=f"esave_{ekey}"):
                ev["label"] = new_label.strip() or ev["token"]
                if ev["type"] == "formula":
                    ev["expr"] = (new_expr or "").strip(); ev["out"] = new_out
                elif ev["type"] in ("date", "number", "dur_days", "dur_months"):
                    if new_def and new_def.strip():
                        ev["default_expr"] = new_def.strip()
                    else:
                        ev.pop("default_expr", None)
                # сбросить «тронутость» полей, чтобы новое умолчание применилось
                for tk in list(st.session_state.keys()):
                    if tk.endswith(ekey + "_touched"):
                        st.session_state[tk] = False
                save_data(); st.success("Сохранено."); st.rerun()

    with st.expander("🗑 Удалить переменную совсем (из всех документов)"):
        allv = list(variables())
        if not allv:
            st.caption("Переменных пока нет.")
        else:
            labels = [f"{v['label']}  ·  {{{v['token']}}}"
                      + ("  · системная" if v["token"] in DEFAULT_TOKENS else "") for v in allv]
            dv = st.selectbox("Переменная", labels, key="delsel")
            dtok = allv[labels.index(dv)]["token"]
            if dtok in DEFAULT_TOKENS:
                st.caption("⚠️ Это системная переменная — её используют встроенные типы Freeze / Extension. "
                           "Удаляй только если точно понимаешь последствия.")
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
            sys_note = ("\n\n⚠️ Это **системная** переменная встроенных типов — после удаления "
                        "соответствующие поля в Freeze / Extension могут перестать подставляться."
                        if tok in DEFAULT_TOKENS else "")
            st.warning(f"Точно удалить переменную **{{{tok}}}**?\n\n"
                       f"Используется в: {used}.\n\n"
                       f"Она будет удалена из всех документов и убрана из всех текстов. "
                       f"Это действие необратимо.{sys_note}")
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
    st.markdown(preview_html(text_of(t["key"]), ph, "Имя клиента", sig_enabled(t), highlight_vars=True),
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
                c0 = f"**{e['client']}**  \n<span style='color:gray;font-size:12px'>" \
                     f"создан: {e['date']} · {e['type_name']}</span>"
                if e.get("drive_docx"):
                    c0 += f"  \n<a href='{e['drive_docx']}' target='_blank' style='font-size:12px'>📁 в Google Drive</a>"
                c[0].markdown(c0, unsafe_allow_html=True)
                client = e["ctx"].get("name", e.get("client", ""))
                esig = e.get("sig", sig_enabled(t))
                docx_bytes = E.build_docx(e["text"], e["ctx"], client, with_signature=esig)
                fname = build_filename(t, e["ctx"], client)
                c[1].download_button("⬇️ .docx", docx_bytes, file_name=fname + ".docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"dl_{t['key']}_{i}", use_container_width=True)
                if E._find_soffice():
                    try:
                        pdf_bytes = cached_pdf(e["text"], json.dumps(e["ctx"], ensure_ascii=False), client, esig)
                        c[2].download_button("⬇️ PDF", pdf_bytes, file_name=fname + ".pdf",
                            mime="application/pdf", key=f"dlp_{t['key']}_{i}", use_container_width=True)
                    except Exception:
                        c[2].caption("PDF —")
                if c[3].button("✏️ Изменить", key=f"edit_{t['key']}_{i}", use_container_width=True):
                    repopulate(t, e.get("form", {}), e.get("extra", {}), e.get("ctx", {}))
                    goto(t["key"], "create")
                    st.session_state.step = 1
                    st.rerun()
                with c[4].popover("🗑", use_container_width=True):
                    st.write("Удалить документ безвозвратно?")
                    if st.button("Да, удалить", key=f"deldoc_{t['key']}_{i}", type="primary"):
                        saved.pop(i); save_data(); st.rerun()
