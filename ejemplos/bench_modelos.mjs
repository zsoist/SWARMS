#!/usr/bin/env node
/**
 * scripts/bench_modelos.mjs
 *
 * Cara a cara: DeepSeek Flash vs GLM 5.3 Flash, los dos por OpenRouter.
 *
 * Uso:
 *   node scripts/bench_modelos.mjs [ruta/salida.json] [--reps=3]
 *   Sin ruta guarda scripts/bench_modelos_salida.json
 *
 * HECHOS VERIFICADOS CONTRA LA API (no tocar):
 *   - El ID real de GLM es z-ai/glm-5.3-flash (el slug con ~ de la web de
 *     comparacion NO es valido).
 *   - Precios USD por millon de tokens: DeepSeek Flash 0.12 / 0.48,
 *     GLM 5.3 Flash 0.15 / 0.50.
 *   - GLM RECHAZA {"reasoning":{"enabled":false}} con 400: "Reasoning is
 *     mandatory for this endpoint and cannot be disabled.". Lo que SI funciona
 *     es {"reasoning":{"effort":"low"}}.
 *   - Sin effort low el razonamiento se come el max_tokens y content vuelve
 *     VACIO.
 *   - GLM NO existe en la API nativa de DeepSeek: hay que ir directo a
 *     OpenRouter.
 *
 * Por eso aqui se manda reasoning.effort="low" a AMBOS modelos y
 * max_tokens=300, para que la comparacion sea justa.
 */

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const AQUI = dirname(fileURLToPath(import.meta.url));
const RAIZ = resolve(AQUI, '..');

const URL_OPENROUTER = 'https://openrouter.ai/api/v1/chat/completions';
const SALIDA_POR_DEFECTO = join(AQUI, 'bench_modelos_salida.json');

const MAX_TOKENS = 300;
const TEMPERATURA = 0;
const REASONING = { effort: 'low' };
const REPETICIONES = 3;
const TIMEOUT_MS = 90000;
const REINTENTOS = 2;

const MODELOS = [
  { id: 'deepseek/deepseek-v4.1-flash', etiqueta: 'DeepSeek Flash', precio_entrada: 0.12, precio_salida: 0.48 },
  { id: 'z-ai/glm-5.3-flash', etiqueta: 'GLM 5.3 Flash', precio_entrada: 0.15, precio_salida: 0.50 },
];

const PALABRA_PROHIBIDA = 'descuento';

/* ------------------------------------------------------------------ */
/* .env (mismo parseo que scripts/experimento/careo_ecp.mjs)           */
/* ------------------------------------------------------------------ */

function parsearEnv(texto) {
  const valores = {};
  for (const cruda of String(texto).split(/\r?\n/)) {
    const linea = cruda.replace(/^\uFEFF/, '');
    if (!linea.trim() || /^\s*#/.test(linea)) continue;
    const limpia = linea.startsWith('export ') ? linea.slice(7) : linea;
    const m = limpia.match(/^\s*([A-Za-z_][A-Za-z0-9_.]*)\s*=\s*(.*)$/);
    if (!m) continue;
    let valor = m[2].trim();
    const entreComillas =
      (valor.startsWith('"') && valor.endsWith('"')) ||
      (valor.startsWith("'") && valor.endsWith("'"));
    if (entreComillas && valor.length >= 2) valor = valor.slice(1, -1);
    valores[m[1]] = valor;
  }
  return valores;
}

function cargarEnv() {
  const valores = {};
  for (const ruta of [join(RAIZ, '.env'), join(AQUI, '.env')]) {
    try {
      Object.assign(valores, parsearEnv(readFileSync(ruta, 'utf8')));
    } catch {
      /* no existe: se ignora */
    }
  }
  return valores;
}

const ENV = cargarEnv();
const API_KEY = process.env.OPENROUTER_API_KEY || ENV.OPENROUTER_API_KEY || '';

/* ------------------------------------------------------------------ */
/* Evaluadores: definen que cuenta como exito en cada tipo de tarea    */
/* ------------------------------------------------------------------ */

const META_LANGUAGE = [
  'as an ai',
  'as a language model',
  'i cannot',
  "i can't",
  'como modelo de lenguaje',
  'no puedo ayudar',
  'lo siento, pero no puedo',
];

const CONECTORES_ES = [
  ' que ', ' la ', ' el ', ' los ', ' las ', ' un ', ' una ', ' es ', ' no ',
  ' si ', ' si ', ' muy ', ' con ', ' para ', ' pero ', ' porque ', ' aqui ',
  ' pues ', ' usted ', ' y ', ' de ', ' le ', ' se ', ' mi ', ' don ',
];

function normalizar(s) {
  return String(s || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

function evaluarVoz(texto) {
  const t = String(texto || '').trim();
  if (!t) return { ok: false, motivo: 'salida vacia' };
  const minus = t.toLowerCase();
  const meta = META_LANGUAGE.find((p) => minus.includes(p));
  if (meta) return { ok: false, motivo: 'rompio personaje ("' + meta + '")' };
  const palabras = t.split(/\s+/).filter((p) => /[a-zA-ZaeiouAEIOU]/.test(p));
  if (palabras.length < 4) return { ok: false, motivo: 'demasiado corto (' + palabras.length + ' palabras)' };
  if (palabras.length > 60) return { ok: false, motivo: 'demasiado largo (' + palabras.length + ' palabras), se pidieron 1-2 frases' };
  const frases = t.split(/[.!?\n]+/).map((s) => s.trim()).filter(Boolean);
  if (frases.length > 4) return { ok: false, motivo: frases.length + ' frases, se pidieron 1-2' };
  const conector = CONECTORES_ES.find((c) => normalizar(t).includes(c.trim()) && minus.includes(c));
  if (!conector) return { ok: false, motivo: 'no se detecta espanol natural' };
  if (/```/.test(t)) return { ok: false, motivo: 'metio bloque de codigo' };
  return { ok: true, motivo: palabras.length + ' palabras / ' + frases.length + ' frase(s), espanol OK' };
}

function evaluarJson(texto) {
  const t = String(texto || '').trim();
  if (!t) return { ok: false, motivo: 'salida vacia' };
  const limpio = t.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  let obj;
  try {
    obj = JSON.parse(limpio);
  } catch (e) {
    return { ok: false, motivo: 'no parsea a la primera: ' + (e && e.message ? e.message : 'JSON invalido') };
  }
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return { ok: false, motivo: 'la raiz no es un objeto JSON' };
  }
  if (!Array.isArray(obj.parches)) return { ok: false, motivo: 'falta el arreglo "parches"' };
  if (obj.parches.length === 0) return { ok: false, motivo: '"parches" viene vacio' };
  for (const p of obj.parches) {
    if (!p || typeof p.buscar !== 'string' || typeof p.reemplazar !== 'string' || !p.buscar) {
      return { ok: false, motivo: 'parche sin buscar/reemplazar validos' };
    }
  }
  const extra = Object.keys(obj).filter((k) => k !== 'parches');
  if (extra.length) return { ok: false, motivo: 'claves extra fuera del contrato: ' + extra.join(', ') };
  if (limpio !== t) return { ok: false, motivo: 'traia texto alrededor del JSON' };
  return { ok: true, motivo: obj.parches.length + ' parche(s), parsea a la primera' };
}

function evaluarEscala(texto) {
  const t = String(texto || '').trim();
  if (!t) return { ok: false, motivo: 'salida vacia' };
  const limpio = t.replace(/[.\s]+$/, '').trim();
  const m = limpio.match(/^[1-5]$/);
  if (m) return { ok: true, motivo: 'numero limpio: ' + m[0] };
  const suelto = limpio.match(/\b([1-5])\b/);
  if (suelto) return { ok: false, motivo: 'trae texto alrededor (numero ' + suelto[1] + ')' };
  return { ok: false, motivo: 'no devolvio un numero del 1 al 5' };
}

function evaluarNegativa(texto) {
  const t = String(texto || '').trim();
  if (!t) return { ok: false, motivo: 'salida vacia' };
  if (/\bdescuentos?\b/.test(normalizar(t))) {
    return { ok: false, motivo: 'uso la palabra prohibida "' + PALABRA_PROHIBIDA + '"' };
  }
  const palabras = t.split(/\s+/).filter(Boolean).length;
  if (palabras < 5) return { ok: false, motivo: 'respuesta demasiado corta (' + palabras + ' palabras)' };
  return { ok: true, motivo: 'obedecio la prohibicion (' + palabras + ' palabras)' };
}

/* ------------------------------------------------------------------ */
/* Tareas: lo que de verdad le importa a este proyecto                 */
/* ------------------------------------------------------------------ */

const TAREAS = [
  {
    id: 'voz_colombiana',
    tipo: 'voz',
    descripcion: 'Voz colombiana: boyacense de 58 anos, vendedor, 1-2 frases, espanol correcto',
    system:
      'Eres don Efrain Rojas, un vendedor boyacense de 58 anos, criado en Tinjaca. ' +
      'Llevas 40 anos detras de un mostrador de plaza. Hablas con calma, tuteas de usted y ' +
      'usas expresiones boyacenses ("sumerce", "vea pues", "de una", "quien dijo miedo"). ' +
      'Jamas suenas a robot, a locutor de noticias ni a asistente virtual. ' +
      'Respondes en una o dos frases cortas, naturales y en espanol colombiano.',
    prompt:
      'Un cliente llega y le dice: "Don Efrain, esa panela si es de verdad de Guepsa o es ' +
      'de las que traen por bultos de Sogamoso?". Contestele como si estuviera en el mostrador.',
    evaluar: evaluarVoz,
  },
  {
    id: 'json_estricto',
    tipo: 'json',
    descripcion: 'JSON estricto: SOLO {"parches":[{"buscar":"x","reemplazar":"y"}]} sin texto alrededor',
    system:
      'Eres un motor de parches de codigo. Devuelves EXCLUSIVAMENTE JSON valido que cumple el ' +
      'contrato pedido. Nunca explicas, nunca saludas, nunca usas bloques de codigo y nunca ' +
      'escribes texto antes o despues del JSON.',
    prompt:
      'Devuelve SOLO un objeto JSON con esta forma exacta: {"parches":[{"buscar":"x","reemplazar":"y"}]}. ' +
      'Aplica este cambio al archivo fuente: reemplaza la cadena "const puerto = 3000;" por ' +
      '"const puerto = 8080;". Un solo parche, sin texto alrededor, sin explicaciones, sin markdown.',
    evaluar: evaluarJson,
  },
  {
    id: 'escala_numerica',
    tipo: 'escala',
    descripcion: 'Escala: contestar SOLO un numero del 1 al 5',
    system:
      'Eres un encuestado. Contestas con un unico digito del 1 al 5. Nunca escribes palabras, ' +
      'puntuacion, comillas ni explicaciones. Solo el digito.',
    prompt:
      'Encuesta: "Que tan probable es que recomiende esta tienda a un vecino?" ' +
      'Responde unicamente con un numero entero del 1 al 5. Nada mas: ni texto, ni el numero escrito en letras.',
    evaluar: evaluarEscala,
  },
  {
    id: 'instruccion_negativa',
    tipo: 'negativa',
    descripcion: 'Instruccion negativa: prohibido usar la palabra "descuento"',
    system:
      'Eres el encargado de una tienda de barrio en Duitama. Hablas claro, en dos o tres frases, ' +
      'y respetas al pie de la letra las palabras prohibidas que te indiquen.',
    prompt:
      'Un cliente te pregunta por el precio de la promocion de temporada. Explicaselo en dos o tres frases. ' +
      'PROHIBIDO TERMINANTEMENTE usar la palabra "descuento", ni en singular ni en plural. ' +
      'Puedes decir "rebaja", "precio especial", "promocion" o "precio de temporada".',
    evaluar: evaluarNegativa,
  },
];

/* ------------------------------------------------------------------ */
/* HTTP                                                                */
/* ------------------------------------------------------------------ */

function dormir(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function peticionUnica(cuerpo) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(URL_OPENROUTER, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + API_KEY,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://build-day.local/bench_modelos',
        'X-Title': 'bench_modelos',
      },
      body: JSON.stringify(cuerpo),
      signal: ctrl.signal,
    });
    let json = null;
    try {
      json = await r.json();
    } catch {
      json = null;
    }
    return { ok: r.ok, status: r.status, json };
  } finally {
    clearTimeout(timer);
  }
}

async function correrUna(modelo, tarea, repeticion) {
  const cuerpo = {
    model: modelo.id,
    messages: [
      ...(tarea.system ? [{ role: 'system', content: tarea.system }] : []),
      { role: 'user', content: tarea.prompt },
    ],
    max_tokens: MAX_TOKENS,
    temperature: TEMPERATURA,
    reasoning: { effort: REASONING.effort },
    usage: { include: true },
  };

  const t0 = Date.now();
  let json = null;
  let status = null;
  let error = null;

  for (let intento = 1; intento <= REINTENTOS; intento++) {
    try {
      const r = await peticionUnica(cuerpo);
      status = r.status;
      json = r.json;
      if (r.ok) {
        error = null;
        break;
      }
      error = (r.json && r.json.error && r.json.error.message) || 'HTTP ' + r.status;
      if (intento < REINTENTOS && (r.status === 429 || r.status >= 500)) {
        await dormir(1200 * intento);
        continue;
      }
      break;
    } catch (e) {
      json = null;
      error = e && e.name === 'AbortError' ? 'timeout tras ' + TIMEOUT_MS + ' ms' : (e && e.message) || String(e);
      if (intento < REINTENTOS) {
        await dormir(1200 * intento);
        continue;
      }
    }
  }

  const latencia_ms = Date.now() - t0;
  const msg = json && json.choices && json.choices[0] && json.choices[0].message;
  const texto = msg && typeof msg.content === 'string' ? msg.content : '';
  const uso = (json && json.usage) || {};
  const prompt_tokens = Number(uso.prompt_tokens) || 0;
  const completion_tokens = Number(uso.completion_tokens) || 0;
  const total_tokens = Number(uso.total_tokens) || prompt_tokens + completion_tokens;
  const reasoning_tokens =
    Number(uso.completion_tokens_details && uso.completion_tokens_details.reasoning_tokens) || 0;
  const costo_usd = Number(
    ((prompt_tokens / 1e6) * modelo.precio_entrada + (completion_tokens / 1e6) * modelo.precio_salida).toFixed(8)
  );
  const vacia = texto.trim().length === 0;
  const evaluacion = error ? { ok: false, motivo: 'error: ' + error } : tarea.evaluar(texto);

  return {
    modelo: modelo.etiqueta,
    modelo_id: modelo.id,
    tarea: tarea.id,
    tipo: tarea.tipo,
    repeticion,
    latencia_ms,
    http_status: status,
    tokens: {
      prompt: prompt_tokens,
      completion: completion_tokens,
      total: total_tokens,
      reasoning: reasoning_tokens,
    },
    costo_usd,
    vacia,
    ok: !!evaluacion.ok,
    motivo: evaluacion.motivo,
    texto: texto.trim(),
    error,
  };
}

/* ------------------------------------------------------------------ */
/* Resumen y tabla                                                     */
/* ------------------------------------------------------------------ */

function mediana(nums) {
  const v = nums.filter((n) => Number.isFinite(n)).slice().sort((a, b) => a - b);
  if (!v.length) return null;
  const medio = Math.floor(v.length / 2);
  return v.length % 2 ? v[medio] : Math.round((v[medio - 1] + v[medio]) / 2);
}

function pad(s, n) {
  const str = String(s == null ? '' : s);
  return str.length >= n ? str.slice(0, n) : str + ' '.repeat(n - str.length);
}

function resumir(resultados) {
  const tipos = [...new Set(TAREAS.map((t) => t.tipo))];
  const porModelo = MODELOS.map((m) => {
    const propios = resultados.filter((r) => r.modelo_id === m.id);
    const latencias = propios.map((r) => r.latencia_ms);
    const vacias = propios.filter((r) => r.vacia).length;
    const exitos = propios.filter((r) => r.ok).length;
    const costoTotal = propios.reduce((a, r) => a + r.costo_usd, 0);
    return {
      modelo: m.etiqueta,
      modelo_id: m.id,
      llamadas: propios.length,
      errores: propios.filter((r) => r.error).length,
      latencia_mediana_ms: mediana(latencias),
      latencia_min_ms: latencias.length ? Math.min(...latencias) : null,
      latencia_max_ms: latencias.length ? Math.max(...latencias) : null,
      costo_total_usd: Number(costoTotal.toFixed(8)),
      costo_promedio_usd: propios.length ? Number((costoTotal / propios.length).toFixed(8)) : 0,
      tokens_totales: propios.reduce((a, r) => a + r.tokens.total, 0),
      salidas_vacias: vacias,
      tasa_vacias: propios.length ? Number((vacias / propios.length).toFixed(3)) : 0,
      tasa_exito_global: propios.length ? Number((exitos / propios.length).toFixed(3)) : 0,
      por_tipo: tipos.map((tipo) => {
        const delTipo = propios.filter((r) => r.tipo === tipo);
        const ok = delTipo.filter((r) => r.ok).length;
        return {
          tipo,
          ok,
          total: delTipo.length,
          tasa: delTipo.length ? Number((ok / delTipo.length).toFixed(3)) : 0,
        };
      }),
    };
  });
  return { porModelo, tipos };
}

function imprimirTabla(resumen) {
  const anchoModelo = Math.max(14, ...resumen.porModelo.map((m) => m.modelo.length)) + 2;
  const linea = '='.repeat(96);
  console.log('\n' + linea);
  console.log('RESUMEN POR MODELO');
  console.log(linea);
  console.log(
    pad('Modelo', anchoModelo) +
      pad('Lat.mediana', 13) +
      pad('Costo total', 15) +
      pad('Vacias', 9) +
      pad('Exito', 8) +
      pad('Errores', 9) +
      'Tokens'
  );
  for (const m of resumen.porModelo) {
    console.log(
      pad(m.modelo, anchoModelo) +
        pad((m.latencia_mediana_ms == null ? '-' : m.latencia_mediana_ms) + ' ms', 13) +
        pad('$' + m.costo_total_usd.toFixed(6), 15) +
        pad((m.tasa_vacias * 100).toFixed(0) + '%', 9) +
        pad((m.tasa_exito_global * 100).toFixed(0) + '%', 8) +
        pad(String(m.errores), 9) +
        String(m.tokens_totales)
    );
  }
  console.log('\n' + linea);
  console.log('TASA DE EXITO POR TIPO DE TAREA');
  console.log(linea);
  console.log(pad('Tipo', 16) + resumen.porModelo.map((m) => pad(m.modelo, 22)).join(''));
  for (const tipo of resumen.tipos) {
    let fila = pad(tipo, 16);
    for (const m of resumen.porModelo) {
      const d = m.por_tipo.find((x) => x.tipo === tipo) || { ok: 0, total: 0, tasa: 0 };
      fila += pad(d.ok + '/' + d.total + ' (' + (d.tasa * 100).toFixed(0) + '%)', 22);
    }
    console.log(fila);
  }
  console.log(linea);
}

/* ------------------------------------------------------------------ */
/* main                                                                */
/* ------------------------------------------------------------------ */

async function main() {
  const args = process.argv.slice(2);
  const rutaArg = args.find((a) => !a.startsWith('-'));
  const flagReps = args.find((a) => a.startsWith('--reps='));
  const repeticiones = flagReps
    ? Math.max(1, Number(flagReps.split('=')[1]) || REPETICIONES)
    : REPETICIONES;
  const rutaSalida = resolve(process.cwd(), rutaArg || SALIDA_POR_DEFECTO);

  if (!API_KEY) {
    console.error('Falta OPENROUTER_API_KEY (definela en el .env de la raiz o como variable de entorno).');
    process.exit(1);
  }

  console.log('Bench DeepSeek Flash vs GLM 5.3 Flash (OpenRouter)');
  console.log(
    '  tareas: ' + TAREAS.length +
      ' | repeticiones: ' + repeticiones +
      ' | max_tokens: ' + MAX_TOKENS +
      ' | reasoning.effort: ' + REASONING.effort +
      ' | temperatura: ' + TEMPERATURA
  );
  console.log('  salida: ' + rutaSalida + '\n');

  const resultados = [];
  for (const modelo of MODELOS) {
    for (const tarea of TAREAS) {
      for (let r = 1; r <= repeticiones; r++) {
        const res = await correrUna(modelo, tarea, r);
        resultados.push(res);
        const marca = res.error ? 'ERROR' : res.ok ? 'OK' : 'FALLO';
        console.log(
          '  ' +
            pad(modelo.etiqueta, 16) +
            pad(tarea.id, 22) +
            ('#' + r + ' ').padEnd(4) +
            pad(res.latencia_ms + ' ms', 9) +
            pad(res.vacia ? 'VACIA' : '', 7) +
            pad(marca, 7) +
            '— ' + res.motivo
        );
      }
    }
  }

  const resumen = resumir(resultados);
  imprimirTabla(resumen);

  const salida = {
    generado: new Date().toISOString(),
    config: {
      url: URL_OPENROUTER,
      modelos: MODELOS,
      repeticiones,
      max_tokens: MAX_TOKENS,
      temperatura: TEMPERATURA,
      reasoning: REASONING,
      precios_usd_por_millon: MODELOS.reduce((acc, m) => {
        acc[m.id] = { entrada: m.precio_entrada, salida: m.precio_salida };
        return acc;
      }, {}),
    },
    tareas: TAREAS.map((t) => ({
      id: t.id,
      tipo: t.tipo,
      descripcion: t.descripcion,
      system: t.system || null,
      prompt: t.prompt,
    })),
    resumen,
    resultados,
  };

  mkdirSync(dirname(rutaSalida), { recursive: true });
  writeFileSync(rutaSalida, JSON.stringify(salida, null, 2), 'utf8');
  console.log('\nDetalle completo en: ' + rutaSalida);
}

main().catch((e) => {
  console.error('Fallo el bench: ' + ((e && e.stack) || e));
  process.exit(1);
});
