"""
Встроенный редактор шаблона (кастомный Streamlit-компонент).
Текстовое поле + панель форматирования (Ж/К/H1/H2) + кликабельные переменные,
которые вставляются по месту курсора. Возвращает текущий текст.
HTML фронтенда пишется во временную папку при импорте — отдельных файлов
в репозитории не требуется.
"""
import os, tempfile
import streamlit.components.v1 as components

_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;padding:0;}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  .tb{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 6px;}
  .tb button{border:1px solid #c9ccd1;background:#fff;border-radius:6px;padding:4px 10px;
    cursor:pointer;font-size:13px;color:#111;}
  .tb button:hover{background:#f3f4f6;}
  .hint{font-size:12px;color:#888;margin:0 0 6px;}
  .chips{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 8px;}
  .chip{border:1px solid #d7dae0;background:#f3f4f6;border-radius:14px;padding:3px 10px;
    cursor:pointer;font-size:12px;color:#333;}
  .chip:hover{background:#e6e9ee;}
  .chip code{color:#2563eb;}
  textarea{width:100%;box-sizing:border-box;min-height:340px;font-family:ui-monospace,
    SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.55;padding:12px;
    border:1px solid #c9ccd1;border-radius:8px;resize:vertical;}
</style></head>
<body>
  <div class="tb">
    <button data-w="**" title="Жирный"><b>Ж</b></button>
    <button data-w="*" title="Курсив"><i>К</i></button>
    <button data-l="# " title="Заголовок">H1</button>
    <button data-l="## " title="Подзаголовок">H2</button>
  </div>
  <div class="hint">Клик по переменной вставляет её в текст по месту курсора.</div>
  <div class="chips" id="chips"></div>
  <textarea id="ta" spellcheck="false"></textarea>
<script>
  var inited=false, debTimer=null;
  var ta=document.getElementById('ta');
  function post(type, extra){ var m={isStreamlitMessage:true,type:type};
    if(extra){for(var k in extra)m[k]=extra[k];} window.parent.postMessage(m,'*'); }
  function setHeight(){ post('streamlit:setFrameHeight',{height:document.body.scrollHeight+8}); }
  function sendValue(){ post('streamlit:setComponentValue',{value:ta.value,dataType:'json'}); }
  function debounced(){ clearTimeout(debTimer); debTimer=setTimeout(sendValue,350); setHeight(); }
  function insertAtCursor(t){ var s=ta.selectionStart,e=ta.selectionEnd;
    ta.value=ta.value.slice(0,s)+t+ta.value.slice(e); ta.focus();
    ta.selectionStart=ta.selectionEnd=s+t.length; sendValue(); }
  function wrapSel(m){ var s=ta.selectionStart,e=ta.selectionEnd,sel=ta.value.slice(s,e)||'текст';
    ta.value=ta.value.slice(0,s)+m+sel+m+ta.value.slice(e); ta.focus();
    ta.selectionStart=s+m.length; ta.selectionEnd=s+m.length+sel.length; sendValue(); }
  function lineMark(m){ var s=ta.selectionStart, ls=ta.value.lastIndexOf('\n',s-1)+1;
    ta.value=ta.value.slice(0,ls)+m+ta.value.slice(ls); ta.focus();
    ta.selectionStart=ta.selectionEnd=s+m.length; sendValue(); }
  var btns=document.querySelectorAll('.tb button');
  for(var i=0;i<btns.length;i++){(function(b){ b.onclick=function(){
    if(b.getAttribute('data-w')) wrapSel(b.getAttribute('data-w'));
    else lineMark(b.getAttribute('data-l')); };})(btns[i]);}
  ta.addEventListener('input', debounced);
  ta.addEventListener('blur', sendValue);
  function renderChips(vars){ var c=document.getElementById('chips'); c.innerHTML='';
    (vars||[]).forEach(function(v){ var el=document.createElement('span'); el.className='chip';
      el.innerHTML='<code>{'+v[0]+'}</code> '+(v[1]||'');
      el.onclick=(function(tok){return function(){insertAtCursor('{'+tok+'}');};})(v[0]);
      c.appendChild(el); }); setHeight(); }
  function applyTheme(th){ if(th&&th.textColor){ ta.style.color=th.textColor; } }
  window.addEventListener('message', function(ev){ var d=ev.data;
    if(!d || d.type!=='streamlit:render') return; var a=d.args||{};
    if(!inited){ ta.value=a.text||''; inited=true; }
    renderChips(a.variables); applyTheme(d.theme); setHeight(); });
  post('streamlit:componentReady',{apiVersion:1});
  setHeight();
</script></body></html>"""

_DIR = tempfile.mkdtemp(prefix="go_editor_")
with open(os.path.join(_DIR, "index.html"), "w", encoding="utf-8") as _f:
    _f.write(_HTML)

_component = components.declare_component("go_template_editor", path=_DIR)


def template_editor(text: str, variables, key=None):
    """Возвращает текущий текст редактора (str)."""
    return _component(text=text, variables=variables, key=key, default=text)
