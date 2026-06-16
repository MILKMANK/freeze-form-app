"""
Встроенный редактор шаблона (кастомный Streamlit-компонент).
Слева: панель форматирования (Ж/К/H1/H2) + текст. Справа: переменные столбцом,
клик по переменной вставляет её по месту курсора (без прыжка текста).
Возвращает текущий текст.
"""
import os, tempfile
import streamlit.components.v1 as components

_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;padding:0;}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  .row{display:flex;gap:14px;align-items:flex-start;}
  .left{flex:1;min-width:0;}
  .right{width:240px;flex:none;}
  .tb{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 6px;}
  .tb button{border:1px solid #c9ccd1;background:#fff;border-radius:6px;padding:4px 10px;
    cursor:pointer;font-size:13px;color:#111;}
  .tb button:hover{background:#f3f4f6;}
  textarea{width:100%;box-sizing:border-box;min-height:360px;font-family:ui-monospace,
    SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.55;padding:12px;
    border:1px solid #c9ccd1;border-radius:8px;resize:vertical;}
  .vtitle{font-size:13px;font-weight:600;color:#444;margin:0 0 6px;}
  .vhint{font-size:11px;color:#999;margin:0 0 8px;}
  .vcol{display:flex;flex-direction:column;gap:6px;max-height:380px;overflow:auto;}
  .chip{border:1px solid #d7dae0;background:#f6f7f9;border-radius:8px;padding:6px 10px;
    cursor:pointer;font-size:12px;color:#333;text-align:left;line-height:1.3;}
  .chip:hover{background:#eceff3;}
  .chip code{color:#2563eb;display:block;}
  .chip span{color:#777;}
</style></head>
<body>
  <div class="row">
    <div class="left">
      <div class="tb">
        <button data-w="**" title="Жирный"><b>Ж</b></button>
        <button data-w="*" title="Курсив"><i>К</i></button>
        <button data-l="# " title="Заголовок">H1</button>
        <button data-l="## " title="Подзаголовок">H2</button>
      </div>
      <textarea id="ta" spellcheck="false"></textarea>
    </div>
    <div class="right">
      <div class="vtitle">Переменные</div>
      <div class="vhint">Клик вставляет переменную по месту курсора.</div>
      <div class="vcol" id="chips"></div>
    </div>
  </div>
<script>
  var inited=false, debTimer=null;
  var ta=document.getElementById('ta');
  function post(type, extra){ var m={isStreamlitMessage:true,type:type};
    if(extra){for(var k in extra)m[k]=extra[k];} window.parent.postMessage(m,'*'); }
  function setHeight(){ post('streamlit:setFrameHeight',{height:document.body.scrollHeight+8}); }
  function sendValue(){ post('streamlit:setComponentValue',{value:ta.value,dataType:'json'}); }
  function debounced(){ clearTimeout(debTimer); debTimer=setTimeout(sendValue,350); setHeight(); }
  function insertAtCursor(t){ var s=ta.selectionStart,e=ta.selectionEnd;
    ta.value=ta.value.slice(0,s)+t+ta.value.slice(e);
    var np=s+t.length; ta.selectionStart=ta.selectionEnd=np; ta.focus(); sendValue(); }
  function wrapSel(m){ var s=ta.selectionStart,e=ta.selectionEnd,sel=ta.value.slice(s,e)||'текст';
    ta.value=ta.value.slice(0,s)+m+sel+m+ta.value.slice(e);
    ta.selectionStart=s+m.length; ta.selectionEnd=s+m.length+sel.length; ta.focus(); sendValue(); }
  function lineMark(m){ var s=ta.selectionStart, ls=ta.value.lastIndexOf('\n',s-1)+1;
    ta.value=ta.value.slice(0,ls)+m+ta.value.slice(ls);
    ta.selectionStart=ta.selectionEnd=s+m.length; ta.focus(); sendValue(); }
  // Не уводим фокус из textarea при клике по кнопкам/чипам — позиция курсора сохраняется.
  var btns=document.querySelectorAll('.tb button');
  for(var i=0;i<btns.length;i++){(function(b){
    b.addEventListener('mousedown', function(e){ e.preventDefault(); });
    b.onclick=function(){ if(b.getAttribute('data-w')) wrapSel(b.getAttribute('data-w'));
      else lineMark(b.getAttribute('data-l')); };
  })(btns[i]);}
  ta.addEventListener('input', debounced);
  ta.addEventListener('blur', sendValue);
  function renderChips(vars){ var c=document.getElementById('chips'); c.innerHTML='';
    (vars||[]).forEach(function(v){ var el=document.createElement('div'); el.className='chip';
      el.innerHTML='<code>{'+v[0]+'}</code><span>'+(v[1]||'')+'</span>';
      el.addEventListener('mousedown', function(e){ e.preventDefault(); });
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
    return _component(text=text, variables=variables, key=key, default=text)
