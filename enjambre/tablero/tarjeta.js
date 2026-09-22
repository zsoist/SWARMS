/* Encapsulado a propósito: este archivo se carga junto al visor, que ya
   define esc/fmtT en el ámbito global. Un const suelto aquí sería un
   'Identifier already declared' que mata la página completa. */
(function(){
'use strict';
const esc = s => String(s==null?'':s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
if(!document.getElementById('css-tarjeta')){
  const s=document.createElement('style');s.id='css-tarjeta';
  s.textContent=`.ag-card{box-sizing:border-box;font-family:'Silkscreen',monospace}.ag-work{display:flex;align-items:flex-start;gap:8px;background:var(--panel2);border:var(--px) solid;padding:8px;box-shadow:2px 2px 0 #000a;cursor:pointer;color:var(--text);min-width:0}.ag-work:hover{filter:brightness(1.08)}.ag-idle{display:flex;align-items:center;gap:8px;padding:4px 8px;border-bottom:var(--px) solid var(--grid);background:transparent;color:var(--faint);min-height:0;line-height:1}.ag-sprite{width:60px;min-width:60px;height:60px;flex:0 0 60px}.ag-dot{width:8px;height:8px;flex:0 0 8px;animation:ag-late 1s infinite}@keyframes ag-late{0%,100%{opacity:1}50%{opacity:.15}}.ag-head{font-size:9px;letter-spacing:1px;text-transform:uppercase;margin:0}.ag-title{font-size:9px;letter-spacing:1px;text-transform:uppercase;margin:2px 0 4px;line-height:1.35;overflow-wrap:anywhere}.ag-sub{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--dim);line-height:1.5;overflow-wrap:anywhere}.ag-num{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--dim)}.ag-count{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--faint);white-space:nowrap}.ag-res{font-family:'Silkscreen',monospace;font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--dim)}`;
  document.head.appendChild(s);
}

const ETQ = {trabajando:'trabajando', listo:'listo', espera:'en espera'};

window.tarjetaAgente = function(agente, extras){
  const a = agente||{}, x = extras||{};
  const n = esc(a.n);
  const piezas = esc(a.hechas==null?0:a.hechas);
  const modelo = esc(a.modelo||'');
  const count = `<span class="ag-count">${piezas} pieza${+piezas===1?"":"s"}</span>`;

  if(a.estado==='trabajando' && a.tarea){
    const t = a.tarea;
    const color = esc(a.color||'var(--work)');
    const titulo = esc(t.titulo||t.filename||t.id||'—');
    const sub = [];
    if(t.filename) sub.push(esc(t.filename));
    if(t.thinking!=null && t.thinking!=='') sub.push('thinking '+esc(t.thinking));
    const subHtml = sub.length?`<div class="ag-sub">${sub.join(' · ')}</div>`:'';
    const click = x.abrirTarea?` data-abrir="${esc(x.abrirTarea)}" data-tid="${esc(t.id)}" tabindex="0" role="button"`:'';
    return `<div class="ag-card ag-work"${click} style="border-color:${color}" title="${modelo}">`
      +`<span class="ag-dot" style="background:${color}"></span>`
      +`<div class="ag-sprite" data-ag="${n}"></div>`
      +`<div style="min-width:0;flex:1">`
      +`<div class="ag-head" style="color:${color}">agente ${n}</div>`
      +`<div class="ag-title" style="color:${color}">${titulo}</div>`
      +subHtml
      +`</div>${count}</div>`;
  }

  const est = ETQ[a.estado]||a.estado||'—';
  return `<div class="ag-card ag-idle" title="${modelo}">`
    +`<span class="ag-num">agente ${n} · ${esc(est)}</span>`
    +`<span style="flex:1"></span>${count}</div>`;
};

// delegación global única: resuelve el nombre de función en el momento del clic
if(!window.__agClickBound){
  window.__agClickBound = true;
  const fire = el => {
    const fn = el.getAttribute('data-abrir'), id = el.getAttribute('data-tid');
    if(fn && typeof window[fn]==='function') window[fn](id);
  };
  document.addEventListener('click', e => {
    const el = e.target.closest && e.target.closest('.ag-work[data-abrir]');
    if(el) fire(el);
  });
  document.addEventListener('keydown', e => {
    if((e.key==='Enter'||e.key===' ') && e.target.classList && e.target.classList.contains('ag-work') && e.target.hasAttribute('data-abrir')){
      e.preventDefault(); fire(e.target);
    }
  });
}

window.resumenAgentes = function(lista){
  const l = Array.isArray(lista)?lista:[];
  let tr=0, es=0, hechas=0;
  for(const a of l){
    if(!a) continue;
    if(a.estado==='trabajando') tr++;
    else if(a.estado==='espera') es++;
    hechas += (a.hechas!=null? +a.hechas : 0);
  }
  return `${tr} trabajando · ${es} en espera · ${hechas} entregas`;
};
})();
