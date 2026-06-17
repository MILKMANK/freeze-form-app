"""
Встроенный редактор шаблона (кастомный Streamlit-компонент).
Слева: форматирование (Ж/К/H1/H2) + текст с подсветкой {переменных}.
Справа: ВСЕ переменные программы (поиск сверху). Переменная, которая есть в тексте,
показывается активной (синяя, со счётчиком ×N и мусоркой); если её в тексте нет —
приглушена. Клик по переменной вставляет её по курсору. Слева от названия — чекбокс
«обязательно» (доступен только если переменная есть в тексте). Тип указан текстом.
Команды в приложение: {action:'del'} (убрать из текста+списка) и {action:'req',value}.
Возвращает {text, cmd}.
"""
import os, tempfile
import streamlit.components.v1 as components

_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;padding:0;}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  .row{display:flex;gap:14px;align-items:flex-start;}
  .left{flex:1;min-width:0;}
  .right{width:330px;flex:none;}
  .tb{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 6px;}
  .tb button{border:1px solid #c9ccd1;background:#fff;border-radius:6px;padding:4px 10px;
    cursor:pointer;font-size:13px;color:#111;}
  .tb button:hover{background:#f3f4f6;}
  .edwrap{position:relative;}
  .backdrop,.ta{box-sizing:border-box;width:100%;min-height:380px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.55;
    padding:12px;border:1px solid transparent;border-radius:8px;
    white-space:pre-wrap;word-wrap:break-word;overflow-wrap:break-word;}
  .backdrop{position:absolute;inset:0;color:#1a1a1a;overflow:hidden;pointer-events:none;
    background:transparent;margin:0;}
  .ta{position:relative;background:transparent;color:transparent;caret-color:#111;
    border:1px solid #c9ccd1;resize:vertical;display:block;}
  .hl{background:#ede9fe;color:#7c3aed;border-radius:4px;padding:0 2px;}
  .vtitle{font-size:13px;font-weight:600;color:#444;margin:0 0 6px;}
  .vsearch{width:100%;box-sizing:border-box;border:1px solid #d7dae0;border-radius:8px;
    padding:6px 9px;font-size:12px;margin:0 0 8px;}
  .vcol{display:flex;flex-direction:column;gap:6px;max-height:430px;overflow:auto;padding-right:2px;}
  .chip{border:1px solid #d7dae0;background:#f6f7f9;border-radius:8px;padding:7px 9px;cursor:pointer;}
  .chip:hover{background:#eceff3;}
  .chip.dim{opacity:.55;background:#fafbfc;}
  .chiprow{display:flex;align-items:center;gap:7px;}
  .reqbox{margin:0;flex:none;cursor:pointer;}
  .reqbox:disabled{cursor:not-allowed;}
  .tok{font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;color:#7c3aed;font-family:ui-monospace,monospace;}
  .chip.dim .tok{color:#8a8f98;}
  .cnt{font-size:11px;color:#888;background:#fff;border:1px solid #e2e5ea;border-radius:10px;
    padding:0 7px;line-height:18px;white-space:nowrap;}
  .del{border:none;background:transparent;cursor:pointer;font-size:14px;padding:0 2px;opacity:.55;}
  .del:hover{opacity:1;}
  .lbl{display:block;color:#777;font-size:12px;margin-top:3px;line-height:1.3;}
  .ty{color:#9aa0a8;}
  .empty{color:#999;font-size:12px;padding:8px 2px;}
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
      <div class="edwrap">
        <div id="bd" class="backdrop"></div>
        <textarea id="ta" class="ta" spellcheck="false"></textarea>
      </div>
    </div>
    <div class="right">
      <div class="vtitle">Переменные</div>
      <input id="vsearch" class="vsearch" placeholder="поиск переменной…">
      <div class="vcol" id="chips"></div>
    </div>
  </div>
<script>
  var inited=false, debTimer=null, pendingCmd=null, allVars=[];
  var ta=document.getElementById('ta'), bd=document.getElementById('bd'),
      vsearch=document.getElementById('vsearch');
  function post(type, extra){ var m={isStreamlitMessage:true,type:type};
    if(extra){for(var k in extra)m[k]=extra[k];} window.parent.postMessage(m,'*'); }
  function setHeight(){ post('streamlit:setFrameHeight',{height:document.body.scrollHeight+8}); }
  function sendValue(){ post('streamlit:setComponentValue',
    {value:{text:ta.value, cmd:pendingCmd}, dataType:'json'}); pendingCmd=null; }
  function escHtml(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function reEsc(s){ return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'); }
  function countOf(tok){ var m=ta.value.match(new RegExp('\\{'+reEsc(tok)+'\\}','g')); return m?m.length:0; }
  function updateBackdrop(){
    bd.innerHTML = escHtml(ta.value).replace(/\{(\w+)\}/g,'<span class="hl">{$1}</span>') + '\n';
    bd.scrollTop = ta.scrollTop; bd.scrollLeft = ta.scrollLeft;
  }
  function afterEdit(){ updateBackdrop(); updateChips(); sendValue(); }
  function insertAtCursor(t){ var s=ta.selectionStart,e=ta.selectionEnd;
    ta.value=ta.value.slice(0,s)+t+ta.value.slice(e);
    var np=s+t.length; ta.selectionStart=ta.selectionEnd=np; ta.focus(); afterEdit(); }
  function wrapSel(m){ var s=ta.selectionStart,e=ta.selectionEnd,sel=ta.value.slice(s,e)||'текст';
    ta.value=ta.value.slice(0,s)+m+sel+m+ta.value.slice(e);
    ta.selectionStart=s+m.length; ta.selectionEnd=s+m.length+sel.length; ta.focus(); afterEdit(); }
  function lineMark(m){ var s=ta.selectionStart, ls=ta.value.lastIndexOf('\n',s-1)+1;
    ta.value=ta.value.slice(0,ls)+m+ta.value.slice(ls);
    ta.selectionStart=ta.selectionEnd=s+m.length; ta.focus(); afterEdit(); }
  function deleteVar(tok){
    ta.value=ta.value.split('{'+tok+'}').join('');
    pendingCmd={id:String(Date.now())+Math.random(), action:'del', token:tok};
    afterEdit();
  }
  function reqToggle(tok, val){
    pendingCmd={id:String(Date.now())+Math.random(), action:'req', token:tok, value:val};
    sendValue();
  }
  var btns=document.querySelectorAll('.tb button');
  for(var i=0;i<btns.length;i++){(function(b){
    b.addEventListener('mousedown', function(e){ e.preventDefault(); });
    b.onclick=function(){ if(b.getAttribute('data-w')) wrapSel(b.getAttribute('data-w'));
      else lineMark(b.getAttribute('data-l')); };
  })(btns[i]);}
  ta.addEventListener('input', function(){ updateBackdrop(); updateChips();
    clearTimeout(debTimer); debTimer=setTimeout(sendValue,350); setHeight(); });
  ta.addEventListener('scroll', function(){ bd.scrollTop=ta.scrollTop; bd.scrollLeft=ta.scrollLeft; });
  ta.addEventListener('blur', sendValue);
  vsearch.addEventListener('input', filterChips);

  function filterChips(){ var q=(vsearch.value||'').toLowerCase();
    document.querySelectorAll('#chips .chip').forEach(function(n){
      var t=(n.getAttribute('data-tok')||'')+' '+(n.getAttribute('data-lbl')||'');
      n.style.display = (!q || t.toLowerCase().indexOf(q)>=0) ? '' : 'none'; }); }

  function updateChips(){ document.querySelectorAll('#chips .chip').forEach(function(n){
    var tok=n.getAttribute('data-tok'); var c=countOf(tok); var active=c>0;
    n.classList.toggle('dim', !active);
    var cn=n.querySelector('.cnt'); if(cn){ cn.style.display=active?'':'none'; cn.textContent='×'+c; }
    var del=n.querySelector('.del'); if(del) del.style.display=active?'':'none';
    var box=n.querySelector('.reqbox'); if(box){ box.disabled=!active; if(!active) box.checked=false; }
  }); setHeight(); }

  function renderChips(vars){ allVars=vars||[]; var c=document.getElementById('chips'); c.innerHTML='';
    if(!allVars.length){ c.innerHTML='<div class="empty">Переменных пока нет. Создай их ниже.</div>'; setHeight(); return; }
    allVars.forEach(function(v){ var tok=v[0], lbl=v[1]||'', ty=v[2]||'', req=!!v[3];
      var cnt=countOf(tok), active=cnt>0;
      var el=document.createElement('div'); el.className='chip'+(active?'':' dim');
      el.setAttribute('data-tok',tok); el.setAttribute('data-lbl',lbl);
      el.innerHTML='<div class="chiprow">'
        +'<input type="checkbox" class="reqbox" title="Обязательное поле"'+(req?' checked':'')+(active?'':' disabled')+'>'
        +'<span class="tok">{'+tok+'}</span>'
        +'<span class="cnt"'+(active?'':' style="display:none"')+'>×'+cnt+'</span>'
        +'<button class="del" title="Удалить из текста"'+(active?'':' style="display:none"')+'>🗑</button>'
        +'</div><span class="lbl">'+lbl+' · <span class="ty">'+ty+'</span></span>';
      el.addEventListener('mousedown', function(e){
        if(e.target.classList.contains('reqbox')||e.target.classList.contains('del')) return;
        e.preventDefault(); });
      el.onclick=function(ev){ if(ev.target.closest('.del')||ev.target.classList.contains('reqbox')) return;
        insertAtCursor('{'+tok+'}'); };
      el.querySelector('.del').onclick=(function(tk){return function(ev){ ev.stopPropagation();
        if(confirm('Убрать переменную {'+tk+'} из текста этого документа?')) deleteVar(tk); };})(tok);
      el.querySelector('.reqbox').onclick=function(ev){ ev.stopPropagation(); };
      el.querySelector('.reqbox').onchange=(function(tk){return function(ev){
        reqToggle(tk, ev.target.checked); };})(tok);
      c.appendChild(el); }); filterChips(); setHeight(); }
  function applyTheme(th){ if(th&&th.textColor){ bd.style.color=th.textColor; ta.style.caretColor=th.textColor; } }
  window.addEventListener('message', function(ev){ var d=ev.data;
    if(!d || d.type!=='streamlit:render') return; var a=d.args||{};
    if(!inited){ ta.value=a.text||''; inited=true; }
    updateBackdrop(); renderChips(a.variables); applyTheme(d.theme); setHeight(); });
  post('streamlit:componentReady',{apiVersion:1});
  updateBackdrop(); setHeight();
</script></body></html>"""

_DIR = tempfile.mkdtemp(prefix="go_editor_")
with open(os.path.join(_DIR, "index.html"), "w", encoding="utf-8") as _f:
    _f.write(_HTML)

_component = components.declare_component("go_template_editor_v6", path=_DIR)


def template_editor(text: str, variables, key=None):
    """variables: [[token, label, type_label, required_bool], ...]. Возвращает {'text','cmd'}."""
    return _component(text=text, variables=variables, key=key, default={"text": text, "cmd": None})
