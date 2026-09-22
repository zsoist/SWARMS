const pintarActividad = (function () {
  'use strict';

  // El vocabulario real del enjambre (swarm.jsonl), no uno genérico.
  // 'jev' se parte en dos: el juez aprueba, rechaza, o se declara no aplicable.
  const UMBRAL = 0.5;
  function clasificar(e) {
    const ev = String((e && e.event) || e || '').toLowerCase();
    const p = (e && e.payload) || {};
    if (ev === 'plan') return 'plan';
    if (ev === 'start') return 'plan';
    if (ev === 'shipped') return 'entrega';
    if (ev === 'done') return 'ensamblaje';
    if (ev === 'fix' || ev === 'retry' || ev === 'reintento') return 'reintento';
    if (ev === 'jev') {
      if (p.sin_juez) return 'otro';
      return (p.p != null && p.p >= UMBRAL) ? 'aprob' : 'rechazo';
    }
    if (ev === 'error' || ev === 'warn') return 'rechazo';
    return 'otro';
  }

  const ICONOS = {
    plan: 'PLN', entrega: 'ENT', aprob: 'OK!', rechazo: 'COR',
    reintento: 'REI', ensamblaje: 'ENS', otro: '---'
  };

  const FILTROS = [
    { id: 'todo', etiqueta: 'todo' },
    { id: 'entregas', etiqueta: 'entregas' },
    { id: 'inspector', etiqueta: 'inspector' },
    { id: 'problemas', etiqueta: 'problemas' }
  ];

  function pasaFiltro(cat, f) {
    if (f === 'todo') return true;
    if (f === 'entregas') return cat === 'entrega' || cat === 'ensamblaje';
    if (f === 'inspector') return cat === 'aprob' || cat === 'rechazo' || cat === 'reintento';
    if (f === 'problemas') return cat === 'rechazo' || cat === 'reintento';
    return true;
  }

  function tituloDe(e, extras) {
    const t = extras.tareas && extras.tareas[e.task_id];
    return (t && (t.titulo || t.title || t.nombre)) || e.task_id || 'tarea desconocida';
  }

  function numAgente(e, extras) {
    const p = e.payload || {};
    if (p.agente != null) return p.agente + 1;
    if (p.agent != null) return p.agent + 1;
    const t = extras.tareas && extras.tareas[e.task_id];
    /* el visor numera los agentes desde 0; el humano los lee desde 1 */
    if (t && t.agente != null) return t.agente + 1;
    if (t && t.agent != null) return t.agent + 1;
    const m = /a(?:gente)?[-_ ]?(\d+)/i.exec(String(e.task_id || ''));
    return m ? Number(m[1]) : null;
  }

  function pctDe(p) {
    if (p.p != null) return Math.round(p.p * 100);
    if (p.pct != null) return Math.round(p.pct);
    if (p.percent != null) return Math.round(p.percent);
    if (p.progreso != null) return Math.round(p.progreso);
    if (p.score != null) return Math.round(p.score);
    return null;
  }

  // Frase en español según categoría
  function frase(e, cat, extras) {
    const p = e.payload || {};
    const tit = tituloDe(e, extras);
    const pct = pctDe(p);
    switch (cat) {
      case 'plan': {
        if (e.event === 'start') {
          return 'arrancó la corrida: ' + String(p.task || '').slice(0, 70);
        }
        const n = p.total ?? p.num_tareas ?? (Array.isArray(p.tasks) ? p.tasks.length : null);
        return 'el planificador repartió ' + (n != null ? n + ' tareas' : 'las tareas');
      }
      case 'entrega': {
        const a = numAgente(e, extras);
        return (a != null ? 'agente ' + a : 'un agente') + ' entregó ' + tit;
      }
      case 'aprob':
        return 'el inspector aprobó ' + tit + (pct != null ? ' al ' + pct + '%' : '');
      case 'rechazo':
        return 'el inspector pidió corregir ' + tit + (pct != null ? ' (' + pct + '%)' : '');
      case 'reintento': {
        const n = p.intento ?? p.n ?? p.retry;
        return 'reintento' + (n != null ? ' ' + n : '') + ' de ' + tit;
      }
      case 'ensamblaje': {
        const s = p.segundos ?? p.duracion ?? p.tiempo;
        return 'se ensambló el entregable final' + (s != null ? ' en ' + s + 's' : '');
      }
      default:
        if (e.event === 'jev' && p.sin_juez) {
          return 'el inspector se abstuvo en ' + tit +
                 (p.motivo ? ' — ' + String(p.motivo).slice(0, 60) : '');
        }
        if (e.event === 'done') {
          return 'terminó la corrida';
        }
        return String(e.event || 'evento desconocido');
    }
  }

  function render(cont, eventos, extras, filtro, visibles) {
    cont.innerHTML = '';
    extras = extras || {};
    const abrir = extras.abrirTarea;
    const colAg = extras.colorAgente;

    // Orden cronológico descendente: lo último arriba
    const ord = (eventos || []).slice().sort(function (a, b) { return b.ms - a.ms; });

    // Cabecera: título + filtros
    const cab = document.createElement('div');
    cab.className = 'pxa-cab';
    const tit = document.createElement('div');
    tit.className = 'pxf pxa-titulo';
    tit.textContent = 'ACTIVIDAD';
    cab.appendChild(tit);

    const fila = document.createElement('div');
    fila.className = 'pxa-filtros';
    FILTROS.forEach(function (f) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'pxf pxa-filtro' + (f.id === filtro ? ' pxa-on' : '');
      b.textContent = f.etiqueta;
      b.addEventListener('click', function () {
        cont._pxaFiltro = f.id;
        cont._pxaVis = 60;
        render(cont, eventos, extras, f.id, 60);
      });
      fila.appendChild(b);
    });
    cab.appendChild(fila);
    cont.appendChild(cab);

    // Lista filtrada
    const lista = ord.filter(function (e) { return pasaFiltro(clasificar(e), filtro); });

    // Recorte a los más recientes
    const MAX = 60;
    visibles = visibles || MAX;
    const corte = lista.slice(0, visibles);

    const caja = document.createElement('div');
    caja.className = 'pxa-lista';

    if (!corte.length) {
      const vacio = document.createElement('div');
      vacio.className = 'pxa-vacio';
      vacio.textContent = 'sin eventos en este filtro';
      caja.appendChild(vacio);
    }

    corte.forEach(function (e) {
      const cat = clasificar(e);
      const fila = document.createElement('div');
      fila.className = 'pxa-linea pxa-' + cat;
      if (e.task_id && abrir) fila.classList.add('pxa-click');

      // Instante relativo
      const t0 = extras.t0 || 0;
      const fmt = extras.fmtT || function (d) { return (d / 1000).toFixed(1) + 's'; };
      const ti = document.createElement('span');
      ti.className = 'pxf pxa-t';
      ti.textContent = '+' + fmt(Math.max(0, e.ms - t0));
      fila.appendChild(ti);

      // Ícono de texto
      const ic = document.createElement('span');
      ic.className = 'pxf pxa-ic';
      ic.textContent = ICONOS[cat];
      fila.appendChild(ic);

      // Frase
      const fr = document.createElement('span');
      fr.className = 'pxa-frase';
      fr.textContent = frase(e, cat, extras);
      fila.appendChild(fr);

      // Clic en líneas con tarea
      if (e.task_id && abrir) {
        fila.addEventListener('click', function () { abrir(e.task_id); });
      }
      caja.appendChild(fila);
    });

    cont.appendChild(caja);

    // Botón para ver eventos anteriores
    if (lista.length > visibles) {
      const mas = document.createElement('button');
      mas.type = 'button';
      mas.className = 'pxf pxa-mas';
      mas.textContent = 'ver los ' + (lista.length - visibles) + ' anteriores';
      mas.addEventListener('click', function () {
        cont._pxaVis = visibles + 60;
        render(cont, eventos, extras, filtro, cont._pxaVis);
      });
      cont.appendChild(mas);
    }
  }

  return function pintarActividad(contenedor, eventos, extras) {
    if (!contenedor) return;

    // Estilos inyectados una sola vez
    if (!pintarActividad._estilos) {
      pintarActividad._estilos = true;
      const st = document.createElement('style');
      st.textContent =
        '.pxa-root{box-sizing:border-box;height:100%;display:flex;flex-direction:column;background:var(--panel);border:3px solid var(--text);box-shadow:2px 2px 0 #000a;padding:8px;min-height:0}' +
        '.pxa-root *{box-sizing:border-box}' +
        '.pxa-cab{flex:0 0 auto;border-bottom:3px solid var(--grid);padding-bottom:6px;margin-bottom:6px}' +
        '.pxa-titulo{font-size:11px;letter-spacing:2px;color:var(--text);margin-bottom:6px}' +
        '.pxa-filtros{display:flex;gap:6px;flex-wrap:wrap}' +
        '.pxa-filtro{font-family:inherit;font-size:9px;background:var(--panel2);color:var(--dim);border:3px solid var(--grid);box-shadow:2px 2px 0 #000a;padding:3px 8px;cursor:pointer;text-transform:uppercase}' +
        '.pxa-filtro:hover{color:var(--text);border-color:var(--text)}' +
        '.pxa-filtro.pxa-on{background:var(--accent);color:#000;border-color:var(--text);color:var(--bg)}' +
        '.pxa-lista{flex:1 1 auto;overflow-y:auto;min-height:0;display:flex;flex-direction:column}' +
        '.pxa-linea{display:flex;align-items:baseline;gap:8px;padding:4px 6px;border-bottom:1px solid var(--grid);font-size:14px;line-height:1.35}' +
        '.pxa-click{cursor:pointer}' +
        '.pxa-click:hover{background:var(--panel2)}' +
        '.pxa-t{font-size:9px;color:var(--faint);flex:0 0 auto;min-width:52px;text-align:right}' +
        '.pxa-ic{font-size:9px;flex:0 0 auto;padding:1px 4px;border:2px solid var(--grid);color:var(--dim)}' +
        '.pxa-frase{color:var(--text)}' +
        '.pxa-plan .pxa-ic{border-color:var(--accent);color:var(--accent)}' +
        '.pxa-entrega .pxa-ic,.pxa-ensamblaje .pxa-ic{border-color:var(--work);color:var(--work)}' +
        '.pxa-aprob .pxa-ic{border-color:var(--ok);color:var(--ok)}' +
        '.pxa-rechazo .pxa-ic,.pxa-reintento .pxa-ic{border-color:var(--fail);color:var(--fail)}' +
        '.pxa-otro .pxa-frase{color:var(--dim);font-size:12px}' +
        '.pxa-vacio{color:var(--faint);font-size:12px;padding:10px 6px}' +
        '.pxa-mas{font-family:inherit;font-size:9px;flex:0 0 auto;margin-top:6px;background:var(--panel2);color:var(--accent);border:3px solid var(--grid);box-shadow:2px 2px 0 #000a;padding:4px 10px;cursor:pointer;text-transform:uppercase}' +
        '.pxa-mas:hover{border-color:var(--accent)}';
      document.head.appendChild(st);
    }

    // El contenedor ES la caja raíz del panel
    contenedor.classList.add('pxa-root');
    const f = contenedor._pxaFiltro || 'todo';
    const v = contenedor._pxaVis || 60;
    render(contenedor, eventos, extras, f, v);
  };
})();

window.pintarActividad = pintarActividad;