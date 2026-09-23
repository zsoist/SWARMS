// Mide a cada proveedor de OpenRouter SOLO (allow_fallbacks:false) con un prompt
// real: tiempo, si terminó, cuánto razonó y si la respuesta sirve. Así se eligió
// la ruta de GLM en enjambre/nucleo.py (AFINADO). Los proveedores cambian cada
// semana: si una corrida se pone lenta o vacía, vuelve a medir antes de tocar código.
//
//   OPENROUTER_API_KEY=... node ejemplos/banco_proveedores.mjs z-ai/glm-5.3-flash prompt.txt CoreWeave Parasail Friendli
//   EFFORT=medium MAX_TOKENS=32000 node ejemplos/banco_proveedores.mjs z-ai/glm-5.3 plan.txt Baidu "Io Net" Novita
//
// Qué mirar: "fin" debe ser stop (length = el razonamiento se comió el techo);
// "content" > 0; y que la respuesta tenga sustancia (un proveedor contestó en 3 s
// con cero razonamiento y una lista vacía: rápido pero perezoso).
import fs from "node:fs";

const [modelo, archivo, ...proveedores] = process.argv.slice(2);
if (!modelo || !archivo || !proveedores.length) {
  console.error("uso: node banco_proveedores.mjs <modelo> <prompt.txt> <proveedor> [...]"); process.exit(1);
}
const llave = process.env.ENJAMBRE_OPENROUTER_KEY || process.env.OPENROUTER_API_KEY;
const prompt = fs.readFileSync(archivo, "utf8");

async function uno(prov) {
  const t0 = Date.now();
  const body = {
    model: modelo, messages: [{ role: "user", content: prompt }],
    max_tokens: +(process.env.MAX_TOKENS || 24000), temperature: 1.0, top_p: 0.95,
    reasoning: { effort: process.env.EFFORT || "low" }, usage: { include: true },
    provider: { order: [prov], allow_fallbacks: false, require_parameters: true, data_collection: "deny",
                max_price: { prompt: +(process.env.OR_MAX_PROMPT || 1), completion: +(process.env.OR_MAX_COMPLETION || 3) } },
  };
  try {
    const r = await (await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST", headers: { Authorization: "Bearer " + llave, "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: AbortSignal.timeout(+(process.env.TIMEOUT_S || 600) * 1000),
    })).json();
    if (r.error) return console.log(prov.padEnd(15), "ERROR", r.error.code, String(r.error.message).slice(0, 80));
    const c = r.choices[0], t = c.message.content || "";
    console.log(prov.padEnd(15), "s", String(Math.round((Date.now() - t0) / 1000)).padStart(4), "fin", c.finish_reason,
      "content", t.length, "razon", r.usage?.completion_tokens_details?.reasoning_tokens, "$", (+r.usage?.cost || 0).toFixed(4));
  } catch (e) {
    console.log(prov.padEnd(15), "EXC", e.name, Math.round((Date.now() - t0) / 1000), "s");
  }
}
await Promise.all(proveedores.map(uno));
