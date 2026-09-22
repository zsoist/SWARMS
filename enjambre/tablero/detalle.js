(function(){
  // Estilos inyectados una sola vez, clases prefijadas dt-
  function inyectarCss(){
    if(window.__dtDetalleCss)return;
    window.__dtDetalleCss=1;
    const s=document.createElement('style');
    s.textContent=`
.dt-wrap{display:flex;flex-direction:column;gap:8px;min-width:0}
.dt-hist{border:3px solid var(--text);background:var(--panel2);box-shadow:2px 2px 0 #000a;padding:9px 11px;font-size:10px;line-height:1.6;color:var(--text)}
.dt-sec{font-size:9px;color:var(--faint);letter-spacing:1px;margin-top:4px}
.dt-grid{display:grid;grid-template-columns:auto 1fr auto 1fr;gap:5px 12px;border:3px solid var(--grid);background:var(--panel);box-shadow:2px 2px 0 #000a;padding:8px 11px;font-size:11px;align-items:baseline}
.dt-l{font-size:9px;color:var(--faint)}
.dt-v{color:var(--text);word-break:break-word;min-width:0}
.dt-link{color:var(--accent);text-decoration:none;border-bottom:2px solid var(--accent)}
.dt-det{border:3px solid var(--grid);background:var(--panel2);box-shadow:2px 2px 0 #000a}
.dt-det summary{cursor:pointer;list-style:none;display:inline-block;margin:6px;padding:4px 8px;border:3px solid var(--grid);background:var(--panel);box-shadow:2px 2px 0 #000a;font-family:Silkscreen,monospace;font-size:9px;color:var(--accent)}
.dt-det summary::-webkit-details-marker{display:none}
.dt-det summary .dt-oc{display:none}
.dt-det[open] summary .dt-ver{display:none}
.dt-det[open] summary .dt-oc{display:inline}
.dt-pre{white-space:pre-wrap;font-size:11px;line-height:1.55;color:var(--text);padding:8px 11px;border-top:3px solid var(--grid);max-height:280px;overflow:auto}
.dt-pre-uno{border-top:none}
.dt-step{display:flex;gap:10px;align-items:flex-start;border:3px solid var(--grid);background:var(--panel);box-shadow:2px 2px 0 #000a;padding:8px 11px}
.dt-num{font-family:Silkscreen,monospace;font-size:12px;color:var(--accent);min-width:22px;padding-top:1px}
.dt-pct{font-family:Silkscreen,monospace;font-size:14px;min-width:52px}
.dt-body{flex:1;min-width:0}
.dt-dec{font-size:11px;color:var(--text)}
.dt-meta{font-size:10px;color:var(--dim);margin-top:2px}
.dt-diag{font-size:10px;color:var(--fail);margin-top:2px}
.dt-arrow{display:flex;align-items:center;gap:8px;padding:3px 0 3px 16px;border-left:3px solid var(--grid);margin-left:10px;color:var(--dim);font-size:10px}
.dt-glyph{font-family:Silkscreen,monospace;font-size:12px;color:var(--accent)}
.dt-none{font-size:10px;color:var(--faint);border:3px dashed var(--grid);padding:8px 11px}
`;
    document.head.appendChild(s);
  }

  // Criterios fallidos de un intento: claves de diag con valor < 0.5
  function fallas(j){
    if(!j.diag)return[];
    return Object.entries(j.diag).filter(function(e){return e[1]<0.5;}).map(function(e){return e[0];});
  }

  // Color del porcentaje según umbrales del visor
  function colorPct(p){
    if(p==null)return'var(--dim)';
    if(p>=85)return'var(--ok)';
    if(p>=50)return'var(--work)';
    return'var(--fail)';
  }

  // Fragmento de una sola línea para la historia, por intento
  function frag(j,esc){
    if(j.sin_juez||j.p==null)return'sin juez';
    var p=Math.round(j.p*100),fl=fallas(j);
    switch(j.action){
      case'aprobar':return'aprobada al '+p+'%';
      case'fix_con_feedback':return'rechazada al '+p+'%'+(fl.length?' por '+esc(fl.join(', ')):'');
      case'reintentar_pensando_mas':return'insuficiente al '+p+'%, a pensar más';
      case'escalar_a_modelo_pro':return'al '+p+'%, escalada a modelo pro';
      default:return'evaluada al '+p+'%';
    }
  }

  // Decisión del inspector, en español, para la fila del intento
  function decision(j){
    if(j.sin_juez||j.p==null)return'sin juez — '+(j.motivo||'sin motivo registrado');
    switch(j.action){
      case'aprobar':return'el inspector aprobó la entrega';
      case'fix_con_feedback':return'el inspector pidió corrección con feedback';
      case'reintentar_pensando_mas':return'el inspector pidió reintentar pensando más';
      case'escalar_a_modelo_pro':return'el inspector escaló la tarea a un modelo pro';
      default:return'el inspector evaluó la entrega';
    }
  }

  // Qué se hizo entre un intento y el siguiente (la flecha)
  function puente(j){
    switch(j.action){
      case'fix_con_feedback':return'se corrigió con las notas del inspector';
      case'reintentar_pensando_mas':return'se reintentó pensando más';
      case'escalar_a_modelo_pro':return'se reintentó con un modelo pro';
      case'aprobar':return'se continuó';
      default:return'se reintentó';
    }
  }

  window.detalleTarea=function(tarea,jevlog,extras){
    inyectarCss();
    var t=tarea||{},js=jevlog||[];
    var t0=extras.t0,colorAgente=extras.colorAgente,fmtT=extras.fmtT,esc=extras.esc,abrirOtra=extras.abrirOtra;

    // 1. Línea de historia
    var hist;
    var motivSinJuez=null;
    for(var i=0;i<js.length;i++){if(js[i].sin_juez){motivSinJuez=js[i].motivo;break;}}
    var todosSinJuez=js.length>0&&js.every(function(j){return j.sin_juez||j.p==null;});
    if(!js.length){
      hist='Sin inspección — sin registros del juez.';
    }else if(todosSinJuez){
      hist='Sin inspección — '+esc(motivSinJuez||'el juez no evaluó esta tarea')+'.';
    }else if(js.length===1){
      var j0=js[0];
      if(j0.action==='aprobar'&&j0.p!=null&&!j0.sin_juez){
        hist='Aprobada al primer intento, '+Math.round(j0.p*100)+'%.';
      }else{
        hist='De un solo intento: '+frag(j0,esc)+'.';
      }
    }else{
      hist='Se intentó '+js.length+' veces: '+js.map(function(j){return frag(j,esc);}).join(', ')+'.';
    }

    // 2. Datos en dos columnas compactas
    var deps=(t.deps||[]).map(function(d){
      return'<a href="#" class="dt-link" onclick="'+abrirOtra+'(\''+esc(d)+'\');return false">'+esc(d)+'</a>';
    }).join(' · ')||'nada — arranca de una';
    var estadoCol=t.status==='ok'?'var(--ok)':colorAgente;
    var datos=
      '<div class="dt-l pxf">estado</div><div class="dt-v"><span style="color:'+estadoCol+'">'+(t.status==='ok'?'entregada':'en curso')+(t.fixed?' (con fixes)':'')+'</span></div>'+
      '<div class="dt-l pxf">agente</div><div class="dt-v"><span style="color:'+colorAgente+'">agente '+(t.agent!=null?t.agent+1:'?')+' · '+esc(extras.modelo||'tropa')+'</span></div>'+
      '<div class="dt-l pxf">thinking</div><div class="dt-v">'+esc(t.thinking||'none')+'</div>'+
      '<div class="dt-l pxf">archivo</div><div class="dt-v">'+esc(t.archivo||t.filename||(t.id||'tarea')+'.md')+'</div>'+
      '<div class="dt-l pxf">tiempo</div><div class="dt-v">'+(t.doneMs!=null?esc(fmtT(t.doneMs,t0)):'—')+'</div>'+
      '<div class="dt-l pxf">depende de</div><div class="dt-v">'+deps+'</div>';

    // 3. La orden recibida, plegable si es larga
    var pr=t.prompt||'—';
    var ordenHtml;
    if(pr.length>300){
      ordenHtml='<details class="dt-det"><summary><span class="dt-ver">ver orden completa</span><span class="dt-oc">ocultar orden</span></summary><div class="dt-pre">'+esc(pr)+'</div></details>';
    }else{
      ordenHtml='<div class="dt-det"><div class="dt-pre dt-pre-uno">'+esc(pr)+'</div></div>';
    }

    // 4. Intentos como secuencia vertical numerada con flechas entre pasos
    var pasos='';
    if(js.length){
      js.forEach(function(j,i){
        var p=(j.p==null?null:Math.round(j.p*100));
        var fl=fallas(j);
        pasos+=
          '<div class="dt-step">'+
            '<div class="dt-num">'+(i+1)+'</div>'+
            '<div class="dt-pct" style="color:'+colorPct(p)+'">'+(p==null?'—':p+'%')+'</div>'+
            '<div class="dt-body">'+
              '<div class="dt-dec">'+esc(decision(j))+'</div>'+
              '<div class="dt-meta">calidad '+(j.quality!=null?Number(j.quality).toFixed(1):'—')+'/4</div>'+
              (fl.length?'<div class="dt-diag">falló: '+esc(fl.join(', '))+'</div>':'')+
            '</div>'+
          '</div>';
        if(i<js.length-1){
          pasos+='<div class="dt-arrow"><span class="dt-glyph">↓</span><span>'+esc(puente(j))+'</span></div>';
        }
      });
    }else{
      pasos='<div class="dt-none">sin inspecciones registradas</div>';
    }

    return'<div class="dt-wrap">'+
      '<div class="dt-hist pxf">'+hist+'</div>'+
      '<div class="dt-sec pxf">DATOS</div>'+
      '<div class="dt-grid">'+datos+'</div>'+
      '<div class="dt-sec pxf">ORDEN RECIBIDA</div>'+
      ordenHtml+
      '<div class="dt-sec pxf">INTENTOS</div>'+
      pasos+
    '</div>';
  };
})();