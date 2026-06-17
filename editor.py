"""
Визуальный редактор шаблона (WYSIWYG). Жирный показывается жирным, заголовки —
заголовками; разметка (** и #) не видна. При сохранении область сериализуется
обратно в markdown (**жирный**, # / ##, {token}), который понимает движок.
Справа — все переменные программы (поиск, активные/приглушённые, ×N, мусорка,
чекбокс «обяз.», тип). Команды в приложение: {action:'del'} и {action:'req',value}.
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
  .editor{box-sizing:border-box;width:100%;min-height:380px;border:1px solid #c9ccd1;border-radius:8px;
    padding:12px;font-family:Georgia,"Times New Roman",serif;font-size:14px;line-height:1.6;outline:none;
    white-space:pre-wrap;word-wrap:break-word;color:#1a1a1a;overflow:auto;}
  .editor:focus{border-color:#7c3aed;}
  .editor h1{font-size:19px;font-weight:700;text-align:center;margin:8px 0;line-height:1.3;}
  .editor h2{font-size:16px;font-weight:700;margin:8px 0;line-height:1.3;}
  .editor div,.editor p{margin:0;min-height:1.6em;}
  .tok{background:#ede9fe;color:#7c3aed;border-radius:4px;padding:0 3px;
    font-family:ui-monospace,monospace;font-size:12px;white-space:nowrap;}
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
  .ctok{font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;
    color:#7c3aed;font-family:ui-monospace,monospace;}
  .chip.dim .ctok{color:#8a8f98;}
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
        <button data-c="bold" title="Жирный"><b>Ж</b></button>
        <button data-c="italic" title="Курсив"><i>К</i></button>
        <button data-b="h1" title="Заголовок">H1</button>
        <button data-b="h2" title="Подзаголовок">H2</button>
      </div>
      <div id="ed" class="editor" contenteditable="true" spellcheck="false"></div>
    </div>
    <div class="right">
      <div class="vtitle">Переменные</div>
      <input id="vsearch" class="vsearch" placeholder="поиск переменной…">
      <div class="vcol" id="chips"></div>
    </div>
  </div>
<script>
  var inited=false, debTimer=null, pendingCmd=null, allVars=[];
  var ed=document.getElementById('ed'), vsearch=document.getElementById('vsearch');
  try{ document.execCommand('styleWithCSS', false, false); }catch(e){}

  function post(type, extra){ var m={isStreamlitMessage:true,type:type};
    if(extra){for(var k in extra)m[k]=extra[k];} window.parent.postMessage(m,'*'); }
  function setHeight(){ post('streamlit:setFrameHeight',{height:document.body.scrollHeight+8}); }
  function sendValue(){ post('streamlit:setComponentValue',
    {value:{text:currentMarkdown(), cmd:pendingCmd}, dataType:'json'}); pendingCmd=null; }
  function scheduleSend(){ clearTimeout(debTimer); debTimer=setTimeout(sendValue,350); }

  function makeChip(tok){ var s=document.createElement('span'); s.className='tok';
    s.setAttribute('contenteditable','false'); s.setAttribute('data-tok',tok);
    s.textContent='{'+tok+'}'; return s; }

  function serNode(n){
    if(n.nodeType===3) return n.nodeValue.replace(/\u200b/g,'');
    if(n.classList && n.classList.contains('tok')) return '{'+n.getAttribute('data-tok')+'}';
    var tag=n.tagName?n.tagName.toLowerCase():'';
    if(tag==='br') return '';
    var inner=serChildren(n);
    if(tag==='b'||tag==='strong') return inner?('**'+inner+'**'):'';
    if(tag==='i'||tag==='em') return inner?('*'+inner+'*'):'';
    return inner;
  }
  function serChildren(n){ var o=''; Array.prototype.forEach.call(n.childNodes,function(c){o+=serNode(c);}); return o; }
  function currentMarkdown(){
    var lines=[], buf=null;
    function flush(){ if(buf!==null){ lines.push(buf); buf=null; } }
    Array.prototype.forEach.call(ed.childNodes, function(n){
      if(n.nodeType===1 && ['DIV','P','H1','H2'].indexOf(n.tagName)>=0){
        flush();
        var pre = n.tagName==='H1'?'# ': n.tagName==='H2'?'## ':'';
        lines.push(pre+serChildren(n));
      } else { if(buf===null) buf=''; buf+=serNode(n); }
    });
    flush();
    return lines.join('\n');
  }

  function parseInline(text, parent){
    var re=/(\{\w+\})|(\*\*([^*]+)\*\*)|(\*([^*]+)\*)/g, last=0, m;
    while((m=re.exec(text))!==null){
      if(m.index>last) parent.appendChild(document.createTextNode(text.slice(last,m.index)));
      if(m[1]){ parent.appendChild(makeChip(m[1].slice(1,-1))); }
      else if(m[2]){ var b=document.createElement('b'); parseInline(m[3],b); parent.appendChild(b); }
      else if(m[4]){ var it=document.createElement('i'); parseInline(m[5],it); parent.appendChild(it); }
      last=re.lastIndex;
    }
    if(last<text.length) parent.appendChild(document.createTextNode(text.slice(last)));
    if(!parent.childNodes.length) parent.appendChild(document.createElement('br'));
  }
  function loadMarkdown(md){
    ed.innerHTML='';
    var lines=(md||'').split('\n');
    if(!lines.length) lines=[''];
    lines.forEach(function(line){
      var tag='div', txt=line;
      if(/^#\s/.test(line)){ tag='h1'; txt=line.replace(/^#\s/,''); }
      else if(/^##\s/.test(line)){ tag='h2'; txt=line.replace(/^##\s/,''); }
      var el=document.createElement(tag); parseInline(txt, el); ed.appendChild(el);
    });
    if(!ed.childNodes.length){ var d=document.createElement('div'); d.appendChild(document.createElement('br')); ed.appendChild(d); }
  }

  function selRange(){ var s=window.getSelection(); if(s && s.rangeCount){ var r=s.getRangeAt(0);
    if(ed.contains(r.startContainer)) return r; } return null; }
  function placeCaretAfter(node){ var r=document.createRange(); r.setStartAfter(node); r.collapse(true);
    var s=window.getSelection(); s.removeAllRanges(); s.addRange(r); }
  function insertNodeAtCaret(node){
    var r=selRange();
    if(!r){ var last=ed.lastChild || ed; (last===ed?ed:last).appendChild(node); return; }
    r.deleteContents(); r.insertNode(node);
  }
  function afterEdit(immediate){ updateChips(); if(immediate){ sendValue(); } else { scheduleSend(); } setHeight(); }

  function insertToken(tok){
    ed.focus(); var chip=makeChip(tok); insertNodeAtCaret(chip);
    var sp=document.createTextNode('\u200b');
    chip.parentNode.insertBefore(sp, chip.nextSibling); placeCaretAfter(sp);
    afterEdit(false);
  }
  function deleteToken(tok){
    Array.prototype.slice.call(ed.querySelectorAll('.tok[data-tok="'+tok+'"]')).forEach(function(n){n.remove();});
    pendingCmd={id:String(Date.now())+Math.random(), action:'del', token:tok};
    afterEdit(true);
  }
  function reqToggle(tok, val){
    pendingCmd={id:String(Date.now())+Math.random(), action:'req', token:tok, value:val}; sendValue();
  }

  function currentBlock(){ var r=selRange(); if(!r) return null; var n=r.startContainer;
    while(n && n!==ed){ if(n.parentNode===ed) return n; n=n.parentNode; } return null; }
  function setBlock(tag){ ed.focus(); var blk=currentBlock();
    var cur=blk?blk.tagName.toLowerCase():''; var to=(cur===tag)?'div':tag;
    try{ document.execCommand('formatBlock', false, '<'+to+'>'); }catch(e){}
    afterEdit(false); }

  var btns=document.querySelectorAll('.tb button');
  for(var i=0;i<btns.length;i++){(function(b){
    b.addEventListener('mousedown', function(e){ e.preventDefault(); });
    b.onclick=function(){ ed.focus();
      if(b.getAttribute('data-c')){ try{document.execCommand(b.getAttribute('data-c'),false,null);}catch(e){} afterEdit(false); }
      else { setBlock(b.getAttribute('data-b')); } };
  })(btns[i]);}

  ed.addEventListener('input', function(){ updateChips(); scheduleSend(); setHeight(); });
  ed.addEventListener('blur', sendValue);
  vsearch.addEventListener('input', filterChips);

  function filterChips(){ var q=(vsearch.value||'').toLowerCase();
    document.querySelectorAll('#chips .chip').forEach(function(n){
      var t=(n.getAttribute('data-tok')||'')+' '+(n.getAttribute('data-lbl')||'');
      n.style.display=(!q || t.toLowerCase().indexOf(q)>=0)?'':'none'; }); }
  function countTok(tok){ return ed.querySelectorAll('.tok[data-tok="'+tok+'"]').length; }
  function updateChips(){ document.querySelectorAll('#chips .chip').forEach(function(n){
    var tok=n.getAttribute('data-tok'); var c=countTok(tok); var active=c>0;
    n.classList.toggle('dim', !active);
    var cn=n.querySelector('.cnt'); if(cn){ cn.style.display=active?'':'none'; cn.textContent='×'+c; }
    var del=n.querySelector('.del'); if(del) del.style.display=active?'':'none';
    var box=n.querySelector('.reqbox'); if(box){ box.disabled=!active; if(!active) box.checked=false; }
  }); setHeight(); }

  function renderChips(vars){ allVars=vars||[]; var c=document.getElementById('chips'); c.innerHTML='';
    if(!allVars.length){ c.innerHTML='<div class="empty">Переменных пока нет. Создай их ниже.</div>'; setHeight(); return; }
    allVars.forEach(function(v){ var tok=v[0], lbl=v[1]||'', ty=v[2]||'', req=!!v[3];
      var cnt=countTok(tok), active=cnt>0;
      var el=document.createElement('div'); el.className='chip'+(active?'':' dim');
      el.setAttribute('data-tok',tok); el.setAttribute('data-lbl',lbl);
      el.innerHTML='<div class="chiprow">'
        +'<input type="checkbox" class="reqbox" title="Обязательное поле"'+(req?' checked':'')+(active?'':' disabled')+'>'
        +'<span class="ctok">{'+tok+'}</span>'
        +'<span class="cnt"'+(active?'':' style="display:none"')+'>×'+cnt+'</span>'
        +'<button class="del" title="Убрать из текста"'+(active?'':' style="display:none"')+'>🗑</button>'
        +'</div><span class="lbl">'+lbl+' · <span class="ty">'+ty+'</span></span>';
      el.addEventListener('mousedown', function(e){
        if(e.target.classList.contains('reqbox')||e.target.classList.contains('del')) return;
        e.preventDefault(); });
      el.onclick=function(ev){ if(ev.target.closest('.del')||ev.target.classList.contains('reqbox')) return;
        insertToken(tok); };
      el.querySelector('.del').onclick=(function(tk){return function(ev){ ev.stopPropagation();
        if(confirm('Убрать переменную {'+tk+'} из текста этого документа?')) deleteToken(tk); };})(tok);
      el.querySelector('.reqbox').onclick=function(ev){ ev.stopPropagation(); };
      el.querySelector('.reqbox').onchange=(function(tk){return function(ev){ reqToggle(tk, ev.target.checked); };})(tok);
      c.appendChild(el); }); filterChips(); setHeight(); }

  window.addEventListener('message', function(ev){ var d=ev.data;
    if(!d || d.type!=='streamlit:render') return; var a=d.args||{};
    if(!inited){ loadMarkdown(a.text||''); inited=true; }
    renderChips(a.variables); setHeight(); });
  post('streamlit:componentReady',{apiVersion:1});
  setHeight();
</script></body></html>"""

_DIR = tempfile.mkdtemp(prefix="go_editor7_")
with open(os.path.join(_DIR, "index.html"), "w", encoding="utf-8") as _f:
    _f.write(_HTML)

_component = components.declare_component("go_template_editor_v7", path=_DIR)


def template_editor(text: str, variables, key=None):
    """variables: [[token, label, type_label, required_bool], ...]. Возвращает {'text','cmd'}."""
    return _component(text=text, variables=variables, key=key, default={"text": text, "cmd": None})
