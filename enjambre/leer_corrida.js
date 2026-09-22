/* Convierte los eventos crudos de una corrida en la historia que se puede leer:
   qué se pidió, cómo se repartió, qué intentó cada agente, qué dijo el inspector
   en cada intento y cómo terminó. Es la pieza que hace el visor entendible. */
window.leerCorrida = function (eventos) {
  const c = { reto: "", tareas: new Map(), t0: null, fin: null, costo: {}, etapas: {} };

  for (const e of eventos) {
    if (c.t0 === null && typeof e.t === "number") c.t0 = e.t;
    const rel = typeof e.t === "number" && c.t0 !== null ? e.t - c.t0 : null;

    if (e.event === "start") { c.reto = e.task || ""; c.etapas.reto = rel; }

    else if (e.event === "plan") {
      c.etapas.plan = rel;
      for (const t of e.tasks || []) {
        c.tareas.set(t.id, {
          id: t.id, prompt: t.prompt || "", deps: t.deps || [],
          thinking: t.thinking || "none", archivo: t.filename || "",
          intentos: [], entregado: null, segundos: null, inicio: null, nivel: 0,
        });
      }
      // nivel = profundidad en el DAG, para colocar los nodos por columnas
      const nivel = (id, visto = new Set()) => {
        const t = c.tareas.get(id);
        if (!t || visto.has(id)) return 0;
        visto.add(id);
        return t.deps.length ? 1 + Math.max(...t.deps.map(d => nivel(d, visto))) : 0;
      };
      for (const t of c.tareas.values()) t.nivel = nivel(t.id);
    }

    // el enjambre emite "shipped"; se acepta "ship" por compatibilidad
    else if (e.event === "shipped" || e.event === "ship") {
      const t = c.tareas.get(e.id);
      if (t) {
        t.entregado = e.filename || t.archivo || true;
        t.chars = e.chars ?? null;
        t.aviso = !!e.warn;
        // el evento trae el instante de ENTREGA; el arranque se estima con la
        // duración si viene, y si no, con el instante del plan
        t.fin = rel;
        t.segundos = e.secs ?? e.seconds ?? null;
        t.inicio = t.segundos != null ? rel - t.segundos
                 : (c.etapas.plan ?? 0);
        if (t.segundos == null) t.segundos = Math.max(0.1, rel - t.inicio);
      }
    }

    else if (e.event === "jev") {
      const t = c.tareas.get(e.id);
      // cada evento jev es UN INTENTO: así se lee la secuencia completa
      if (t) t.intentos.push({
        p: e.p ?? null, calidad: e.quality ?? null,
        accion: e.action || "", diag: e.diag || null, cuando: rel,
      });
    }

    else if (e.event === "done") {
      c.fin = e.seconds ?? e.secs ?? rel;
      c.costo = e.spent || e.cost || {};
      c.etapas.ensamblador = rel;
    }
  }

  const tareas = [...c.tareas.values()];
  c.lista = tareas;
  c.resumen = {
    total: tareas.length,
    entregadas: tareas.filter(t => t.entregado).length,
    aprobadas: tareas.filter(t => (t.intentos.at(-1)?.p ?? 0) >= 0.65).length,
    reintentadas: tareas.filter(t => t.intentos.length > 1).length,
    sinInspector: tareas.filter(t => !t.intentos.length).length,
    paralelasMax: maxSolapadas(tareas),
    costoTotal: Object.values(c.costo).reduce((a, b) => a + b, 0),
  };
  return c;
};

/* Cuántas tareas corrieron a la vez en el pico: es la medida real del paralelismo. */
function maxSolapadas(tareas) {
  const marcas = [];
  for (const t of tareas) {
    if (t.inicio == null || t.segundos == null) continue;
    marcas.push([t.inicio, 1], [t.inicio + t.segundos, -1]);
  }
  marcas.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  let n = 0, max = 0;
  for (const [, d] of marcas) { n += d; max = Math.max(max, n); }
  return max;
}

/* Traduce la jerga del inspector a algo que se entienda de una. */
window.ACCION_HUMANA = {
  aprobar: "aprobado",
  fix_con_feedback: "corregir con notas",
  reintentar_pensando_mas: "reintentar pensando más",
  escalar_a_modelo_pro: "escalar a modelo mayor",
};
