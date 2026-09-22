(function () {
  "use strict";

  /* Estilos propios, inyectados una sola vez, con prefijo fl- */
  var CSS_ID = "fl-estilos";
  var CSS = [
    ".fl-raiz{display:flex;flex-direction:column;gap:14px;color:var(--text)}",
    ".fl-bloque{background:var(--panel);border:3px solid var(--grid);box-shadow:2px 2px 0 #000a;padding:10px}",
    ".fl-titulo{font-size:11px;color:var(--dim);letter-spacing:1px;margin-bottom:8px}",
    /* Bloque 1: cadena de valor */
    ".fl-cadena{display:flex;align-items:stretch;gap:0;flex-wrap:wrap}",
    ".fl-etapa{background:var(--panel2);border:3px solid var(--grid);box-shadow:2px 2px 0 #000a;padding:8px 10px;min-width:110px;flex:1 1 0}",
    ".fl-etapa-num{font-size:20px;line-height:1.1}",
    ".fl-etapa-nom{font-size:9px;color:var(--dim);letter-spacing:1px;margin-top:2px}",
    ".fl-etapa-sub{font-size:9px;color:var(--faint);margin-top:4px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    ".fl-flecha{align-self:center;width:0;height:0;border-top:8px solid transparent;border-bottom:8px solid transparent;border-left:10px solid var(--dim);margin:0 6px;flex:0 0 auto}",
    /* Bloque 2: DAG */
    ".fl-dag-scroll{overflow-x:auto;padding-bottom:4px}",
    ".fl-dag-svg text{font-family:inherit}",
    ".fl-nodo{cursor:pointer}",
    ".fl-nodo:hover rect{filter:brightness(1.2)}",
    /* Bloque 3: linea de tiempo */
    ".fl-fila{display:flex;align-items:center;gap:8px;margin-bottom:6px}",
    ".fl-fila-etq{width:170px;flex:0 0 auto;font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}",
    ".fl-pista{flex:1 1 auto;position:relative;height:16px;background:var(--panel2);border:3px solid var(--grid)}",
    ".fl-barra{position:absolute;top:0;height:100%;min-width:4px;box-shadow:2px 2px 0 #000a}",
    ".fl-fila-tiempo{width:64px;flex:0 0 auto;font-size:9px;color:var(--dim);text-align:right}",
    ".fl-eje{position:relative;height:18px;margin:6px 0 0 178px;border-top:3px solid var(--grid)}",
    ".fl-eje-marca{position:absolute;top:0;font-size:8px;color:var(--faint);transform:translateX(-50%);padding-top:2px}",
    ".fl-vacio{font-size:11px;color:var(--dim);padding:16px;text-align:center}"
  ].join("\n");

  function estilos() {
    if (!document.getElementById(CSS_ID)) {
      var s = document.createElement("style");
      s.id = CSS_ID;
      s.textContent = CSS;
      document.head.appendChild(s);
    }
  }

  /* Estado de una tarea segun su ultimo intento ante el inspector */
  function estadoDe(t) {
    var u = t.intentos && t.intentos.length ? t.intentos[t.intentos.length - 1] : null;
    if (!u) return "sin";
    return (u.p == null ? 0 : u.p) >= 0.65 ? "ok" : "fail";
  }

  var COLOR = { ok: "var(--ok)", fail: "var(--fail)", sin: "var(--accent)" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function tituloDe(t) { return (t && t.titulo) ? t.titulo : (t ? t.id : "?"); }

  function fmtSeg(s) {
    if (s == null || isNaN(s)) return "--";
    return (Math.round(s * 10) / 10) + "s";
  }

  function fmtCosto(v) {
    if (v == null || isNaN(v)) return "--";
    return v >= 1 ? v.toFixed(2) : v.toFixed(4);
  }

  function acortar(s, n) {
    s = String(s == null ? "" : s);
    return s.length > n ? s.slice(0, n - 1) + "+" : s;
  }

  /* ---- Bloque 1: cadena de valor ---- */
  function bloqueCadena(c) {
    var r = c.resumen || {};
    var et = c.etapas || {};
    var reto = c.reto || "(sin reto)";
    var planTxt = et.plan != null ? "t+" + fmtSeg(et.plan) : "";
    var insp = (r.aprobadas || 0) + "/" + (r.total || 0);
    var inspSub = (r.reintentadas || 0) + " reintentadas, " + (r.sinInspector || 0) + " sin revisar";
    var etapas = [
      { nom: "RETO", num: "1", sub: acortar(reto, 24), tit: reto },
      { nom: "PLANIFICA", num: String(r.total || 0), sub: "tareas " + planTxt },
      { nom: "EN PARALELO", num: String(r.paralelasMax || 0), sub: "pico simultaneo" },
      { nom: "INSPECTOR", num: insp, sub: inspSub },
      { nom: "ENSAMBLA", num: fmtSeg(c.fin), sub: "tiempo total" },
      { nom: "ENTREGABLE", num: (r.entregadas || 0), sub: "piezas · " + fmtCosto(r.costoTotal) }
    ];
    var h = '<div class="fl-titulo pxf">CADENA DE VALOR</div><div class="fl-cadena">';
    for (var i = 0; i < etapas.length; i++) {
      var e = etapas[i];
      h += '<div class="fl-etapa"' + (e.tit ? ' title="' + esc(e.tit) + '"' : "") + ">"
        + '<div class="fl-etapa-num pxf">' + esc(e.num) + "</div>"
        + '<div class="fl-etapa-nom pxf">' + esc(e.nom) + "</div>"
        + '<div class="fl-etapa-sub">' + esc(e.sub) + "</div></div>";
      if (i < etapas.length - 1) h += '<div class="fl-flecha"></div>';
    }
    return h + "</div>";
  }

  /* ---- Bloque 2: DAG en SVG ---- */
  function bloqueDAG(c) {
    var tareas = c.lista;
    var NW = 150, NH = 42, GX = 56, GY = 16, PAD = 12;
    var porNivel = {};
    var maxNivel = 0;
    tareas.forEach(function (t) {
      var n = t.nivel || 0;
      if (!porNivel[n]) porNivel[n] = [];
      porNivel[n].push(t);
      if (n > maxNivel) maxNivel = n;
    });
    var pos = {}; /* id -> {x, y} */
    var filasMax = 0;
    for (var n = 0; n <= maxNivel; n++) {
      var col = porNivel[n] || [];
      col.sort(function (a, b) { return String(a.id).localeCompare(String(b.id)); });
      if (col.length > filasMax) filasMax = col.length;
      col.forEach(function (t, i) {
        pos[t.id] = { x: PAD + n * (NW + GX), y: PAD + i * (NH + GY) };
      });
    }
    var w = PAD * 2 + maxNivel * (NW + GX) + NW;
    var h = PAD * 2 + Math.max(1, filasMax) * (NH + GY) - GY;

    var s = '<div class="fl-titulo pxf">DEPENDENCIAS (DAG)</div>'
      + '<div class="fl-dag-scroll"><svg class="fl-dag-svg" width="' + w + '" height="' + h + '" '
      + 'viewBox="0 0 ' + w + " " + h + '" xmlns="http://www.w3.org/2000/svg">';

    /* Flechas en angulo recto: horizontal, vertical, horizontal */
    tareas.forEach(function (t) {
      var p = pos[t.id];
      if (!p) return;
      (t.deps || []).forEach(function (d) {
        var q = pos[d];
        if (!q) return;
        var x1 = q.x + NW, y1 = q.y + NH / 2;
        var x2 = p.x, y2 = p.y + NH / 2;
        var xm = (x1 + x2) / 2;
        s += '<path d="M' + x1 + " " + y1 + " H" + xm + " V" + y2 + " H" + x2
          + '" fill="none" stroke="var(--faint)" stroke-width="2"/>';
      });
    });

    /* Nodos */
    tareas.forEach(function (t) {
      var p = pos[t.id];
      if (!p) return;
      var est = estadoDe(t);
      var color = COLOR[est];
      var u = t.intentos && t.intentos.length ? t.intentos[t.intentos.length - 1] : null;
      var pTxt = u && u.p != null ? ("p=" + (Math.round(u.p * 100) / 100)) : "sin inspector";
      s += '<g class="fl-nodo" data-id="' + esc(t.id) + '">'
        + '<rect x="' + p.x + '" y="' + p.y + '" width="' + NW + '" height="' + NH
        + '" fill="var(--panel2)" stroke="' + color + '" stroke-width="3"/>'
        + '<text x="' + (p.x + 8) + '" y="' + (p.y + 18) + '" font-size="10" fill="var(--text)" '
        + 'class="pxf">' + esc(acortar(tituloDe(t), 18)) + "</text>"
        + '<text x="' + (p.x + 8) + '" y="' + (p.y + 33) + '" font-size="9" fill="var(--dim)">'
        + esc(pTxt) + "</text></g>";
    });

    return s + "</svg></div>";
  }

  /* ---- Bloque 3: linea de tiempo ---- */
  function bloqueTiempo(c) {
    var tareas = c.lista;
    var tmax = c.fin || 0;
    tareas.forEach(function (t) {
      if (t.inicio != null && t.segundos != null) {
        var finT = t.inicio + t.segundos;
        if (finT > tmax) tmax = finT;
      }
    });
    if (!(tmax > 0)) tmax = 1;

    var h = '<div class="fl-titulo pxf">LINEA DE TIEMPO</div>';
    tareas.forEach(function (t) {
      var est = estadoDe(t);
      var color = COLOR[est];
      h += '<div class="fl-fila">'
        + '<div class="fl-fila-etq" title="' + esc(tituloDe(t)) + '">' + esc(acortar(tituloDe(t), 24)) + "</div>"
        + '<div class="fl-pista">';
      if (t.inicio != null && t.segundos != null) {
        var izq = Math.max(0, (t.inicio / tmax) * 100);
        var ancho = Math.max(0.8, (t.segundos / tmax) * 100);
        h += '<div class="fl-barra" style="left:' + izq + "%;width:" + ancho + "%;background:" + color + '" title="'
          + esc("inicio " + fmtSeg(t.inicio) + " / duracion " + fmtSeg(t.segundos)) + '"></div>';
      }
      h += "</div>"
        + '<div class="fl-fila-tiempo pxf">' + (t.segundos != null ? esc(fmtSeg(t.segundos)) : "--") + "</div>"
        + "</div>";
    });

    /* Eje de tiempo con 7 marcas */
    h += '<div class="fl-eje">';
    for (var i = 0; i <= 6; i++) {
      h += '<div class="fl-eje-marca" style="left:' + (i / 6 * 100) + '%">' + esc(fmtSeg(tmax * i / 6)) + "</div>";
    }
    return h + "</div>";
  }

  /* ---- Punto de entrada ---- */
  window.pintarFlujo = function (contenedor, corrida) {
    estilos();
    if (!contenedor) return;
    contenedor.innerHTML = "";

    var raiz = document.createElement("div");
    raiz.className = "fl-raiz";

    var tareas = corrida && corrida.lista ? corrida.lista : [];
    if (!tareas.length) {
      raiz.innerHTML = '<div class="fl-bloque pxf" style="font-size:12px">SIN TAREAS: la corrida no produjo plan ni trabajo que mostrar.</div>';
      contenedor.appendChild(raiz);
      return;
    }

    var b1 = document.createElement("div");
    b1.className = "fl-bloque";
    b1.innerHTML = bloqueCadena(corrida);

    var b2 = document.createElement("div");
    b2.className = "fl-bloque";
    b2.innerHTML = bloqueDAG(corrida);

    var b3 = document.createElement("div");
    b3.className = "fl-bloque";
    b3.innerHTML = bloqueTiempo(corrida);

    raiz.appendChild(b1);
    raiz.appendChild(b2);
    raiz.appendChild(b3);
    contenedor.appendChild(raiz);

    /* Clic en nodos del DAG */
    if (typeof window.alTocarTarea === "function") {
      var nodos = b2.querySelectorAll(".fl-nodo");
      for (var i = 0; i < nodos.length; i++) {
        (function (nodo) {
          nodo.addEventListener("click", function () {
            window.alTocarTarea(nodo.getAttribute("data-id"));
          });
        })(nodos[i]);
      }
    }
  };
})();
