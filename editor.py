"""
Встроенный редактор шаблона (кастомный Streamlit-компонент).
Слева: форматирование (Ж/К/H1/H2) + текст. Справа: переменные столбцом —
клик вставляет по курсору; показан счётчик использований; мусорка удаляет
переменную (убирает все её вхождения из текста и шлёт команду удаления в Python).
Возвращает объект {text, cmd}.
"""
import os, tempfile
import streamlit.components.v1 as components

_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;padding:0;}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  .row{display:flex;gap:14px;align-items:flex-start;}
  .left{flex:1;min-width:0;}
  .right{width:320px;flex:none;}
  .tb{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 6px;}
  .tb button{border:1px solid #c9ccd1;background:#fff;border-radius:6px;padding:4px 10px;
    cursor:pointer;font-size:13px;color:#111;}
  .tb button:hover{background:#f3f4f6;}
  textarea{width:100%;box-sizing:border-box;min-height:380px;font-family:ui-monospace,
    SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.55;padding:12px;
    border:1px solid #c9ccd1;border-radius:8px;resize:vertical;}
  .vtitle{font-size:13px;font-weight:600;color:#444;margin:0 0 4px;}
  .vhint{font-size:11px;color:#999;margin:0 0 8px;}
  .vcol{display:flex;flex-direction:column;gap:6px;max-height:420px;overflow:auto;padding-right:2px;}
  .chip{border:1px solid #d7dae0;background:#f6f7f9;border-radius:8px;padding:7px 10px;cursor:pointer;}
  .chip:hover{background:#eceff3;}
  .chiprow{display:flex;align-items:center;gap:8px;}
  .chiprow code{color:#2563eb;font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;}
  .cnt{font-size:11px;color:#888;background:#fff;border:1px solid #e2e5ea;border-radius:10px;
    padding:0 7px;line-height:18px;white-space:nowrap;}
  .del{border:none;background:transparent;cursor:pointer;font-size:14px;padding:0 2px;opacity:.55;}
  .del:hover{opacity:1;}
  .lbl{display:block;color:#777;font-size:12px;margin-top:3px;line-height:1.3;}
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
      <div class="vhint">Клик — вставить по курсору. Мусорка — удалить из текста и из списка.</div>
      <div class="vcol" id="chips"></div>
    </div>
  </div>
<script>
  var inited=false, debTimer=null, pendingCmd=null, lastVars=[];
  var ta=document.getElementById('ta');
  function post(type, extra){ var m={isStreamlitMessage:true,type:type};
    if(extra){for(var k in extra)m[k]=extra[k];} window.parent.postMessage(m,'*'); }
  function setHeight(){ post('streamlit:setFrameHeight',{height:document.body.scrollHeight+8}); }
  function sendValue(){ post('streamlit:setComponentValue',
    {value:{text:ta.value, cmd:pendingCmd}, dataType:'json'}); pendingCmd=null; }
  function debounced(){ clearTimeout(debTimer); debTimer=setTimeout(sendValue,350); updateCounts(); setHeight(); }
  function reEsc(s){ return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'); }
  function countOf(tok){ var m=ta.value.match(new RegExp('\\{'+reEsc(tok)+'\\}','g')); return m?m.length:0; }
  function insertAtCursor(t){ var s=ta.selectionStart,e=ta.selectionEnd;
    ta.value=ta.value.slice(0,s)+t+ta.value.slice(e);
    var np=s+t.length; ta.selectionStart=ta.selectionEnd=np; ta.focus(); sendValue(); updateCounts(); }
  function wrapSel(m){ var s=ta.selectionStart,e=ta.selectionEnd,sel=ta.value.slice(s,e)||'текст';
    ta.value=ta.value.slice(0,s)+m+sel+m+ta.value.slice(e);
    ta.selectionStart=s+m.length; ta.selectionEnd=s+m.length+sel.length; ta.focus(); sendValue(); }
  function lineMark(m){ var s=ta.selectionStart, ls=ta.value.lastIndexOf('\n',s-1)+1;
    ta.value=ta.value.slice(0,ls)+m+ta.value.slice(ls);
    ta.selectionStart=ta.selectionEnd=s+m.length; ta.focus(); sendValue(); }
  function deleteVar(tok){
    ta.value=ta.value.split('{'+tok+'}').join('');           // убрать все вхождения из текста
    pendingCmd={id:String(Date.now())+Math.random(), action:'del', token:tok};
    sendValue(); updateCounts();
  }
  var btns=document.querySelectorAll('.tb button');
  for(var i=0;i<btns.length;i++){(function(b){
    b.addEventListener('mousedown', function(e){ e.preventDefault(); });
    b.onclick=function(){ if(b.getAttribute('data-w')) wrapSel(b.getAttribute('data-w'));
      else lineMark(b.getAttribute('data-l')); };
  })(btns[i]);}
  ta.addEventListener('input', debounced);
  ta.addEventListener('blur', sendValue);
  function updateCounts(){ var c=document.getElementById('chips');
    var nodes=c.querySelectorAll('.chip'); nodes.forEach(function(n){
      var tok=n.getAttribute('data-tok'); var cn=n.querySelector('.cnt');
      if(cn) cn.textContent='×'+countOf(tok); }); }
  function renderChips(vars){ lastVars=vars||[]; var c=document.getElementById('chips'); c.innerHTML='';
    lastVars.forEach(function(v){ var tok=v[0], lbl=v[1]||'';
      var el=document.createElement('div'); el.className='chip'; el.setAttribute('data-tok',tok);
      el.innerHTML='<div class="chiprow"><code>{'+tok+'}</code>'
        +'<span class="cnt">×'+countOf(tok)+'</span>'
        +'<button class="del" title="Удалить переменную">🗑</button></div>'
        +'<span class="lbl">'+lbl+'</span>';
      el.addEventListener('mousedown', function(e){ e.preventDefault(); });
      el.onclick=function(ev){ if(ev.target.closest('.del')) return; insertAtCursor('{'+tok+'}'); };
      el.querySelector('.del').onclick=(function(tk){return function(ev){ ev.stopPropagation();
        if(confirm('Удалить переменную {'+tk+'} из этого документа и из текста?')) deleteVar(tk); };})(tok);
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

_component = components.declare_component("go_template_editor_v4", path=_DIR)


def template_editor(text: str, variables, key=None):
    """Возвращает {'text': str, 'cmd': {...}|None}."""
    return _component(text=text, variables=variables, key=key, default={"text": text, "cmd": None})
