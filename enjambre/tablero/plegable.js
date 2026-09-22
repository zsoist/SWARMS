(function () {
  'use strict';

  if (!document.getElementById('css-plegable')) {
    var st = document.createElement('style');
    st.id = 'css-plegable';
    st.textContent = [
      '.pl-wrap{display:flex;flex-direction:column;}',
      '.pl-cab{display:flex;align-items:center;gap:10px;width:100%;box-sizing:border-box;background:var(--panel);border:0;border-bottom:var(--px) solid var(--grid);padding:9px 12px;cursor:pointer;text-align:left;font:inherit;color:inherit;}',
      '.pl-cab:hover{border-bottom-color:var(--accent);}',
      '.pl-tit{font-family:"Silkscreen",monospace;text-transform:uppercase;font-size:10px;letter-spacing:1px;color:var(--text);white-space:nowrap;flex:0 0 auto;}',
      '.pl-res{color:var(--dim);font-size:11px;flex:1 1 auto;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;}',
      '.pl-chv{color:var(--faint);font-size:11px;flex:0 0 auto;font-family:monospace;}',
      '.pl-cont{background:var(--panel2);}',
      '.pl-cont[aria-hidden="true"]{display:none;}',
      '@media (max-width:759px){.pl-res{display:none;}}'
    ].join('\n');
    document.head.appendChild(st);
  }

  var LLAVE = 'visor.plegables';

  function leerEstado() {
    try {
      var raw = localStorage.getItem(LLAVE);
      if (!raw) return {};
      var obj = JSON.parse(raw);
      return (obj && typeof obj === 'object') ? obj : {};
    } catch (e) {
      return {};
    }
  }

  function escribirEstado(estado) {
    try {
      localStorage.setItem(LLAVE, JSON.stringify(estado));
    } catch (e) { /* almacenamiento no disponible */ }
  }

  var registro = []; // {sel, section, btn, res, cont, titulo}

  function pintar(item, abierta) {
    item.btn.setAttribute('aria-expanded', abierta ? 'true' : 'false');
    item.cont.setAttribute('aria-hidden', abierta ? 'false' : 'true');
    item.cont.style.display = abierta ? '' : 'none';
    item.chv.textContent = abierta ? '▾' : '▸';
  }

  function pintarResumen(item) {
    var texto = '';
    try {
      texto = String(item.resumenFn() || '');
    } catch (e) {
      texto = '';
    }
    item.res.textContent = texto;
  }

  function preparar(item) {
    var section = item.section;

    var wrap = document.createElement('div');
    wrap.className = 'pl-wrap';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pl-cab';

    var tit = document.createElement('span');
    tit.className = 'pl-tit';
    tit.textContent = item.titulo;

    var res = document.createElement('span');
    res.className = 'pl-res';

    var chv = document.createElement('span');
    chv.className = 'pl-chv';
    chv.setAttribute('aria-hidden', 'true');
    chv.textContent = '▸';

    var cont = document.createElement('div');
    cont.className = 'pl-cont';

    // envolver el contenido original: mover todos los hijos de section al cont
    while (section.firstChild) {
      cont.appendChild(section.firstChild);
    }
    var idCont = 'pl-cont-' + Math.random().toString(36).slice(2, 9);
    cont.id = idCont;

    btn.setAttribute('aria-controls', idCont);
    btn.appendChild(tit);
    btn.appendChild(res);
    btn.appendChild(chv);

    wrap.appendChild(btn);
    wrap.appendChild(cont);
    section.appendChild(wrap);

    item.btn = btn;
    item.res = res;
    item.chv = chv;
    item.cont = cont;

    btn.addEventListener('click', function () {
      var abierta = btn.getAttribute('aria-expanded') === 'true';
      var nuevo = !abierta;
      pintar(item, nuevo);
      var estado = leerEstado();
      estado[item.sel] = nuevo;
      escribirEstado(estado);
    });
  }

  window.hacerPlegable = function (config) {
    var cfg = config || {};
    var secciones = cfg.secciones || [];
    var estado = leerEstado();

    for (var i = 0; i < secciones.length; i++) {
      var def = secciones[i];
      var section = document.querySelector(def.sel);
      if (!section) continue;
      if (section.__plegable) continue;

      var item = {
        sel: def.sel,
        section: section,
        titulo: def.titulo || '',
        resumenFn: typeof def.resumen === 'function' ? def.resumen : function () { return ''; }
      };

      section.__plegable = item;
      preparar(item);

      var abierta = Object.prototype.hasOwnProperty.call(estado, def.sel)
        ? !!estado[def.sel]
        : !!def.abierta;

      pintarResumen(item);
      pintar(item, abierta);

      registro.push(item);
    }
  };

  window.refrescarPlegables = function () {
    for (var i = 0; i < registro.length; i++) {
      pintarResumen(registro[i]);
    }
  };
})();