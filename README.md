# SWARMS — enjambre

Un modelo planifica y reparte; muchos baratos ejecutan en paralelo; un juez de
centavos revisa. Es un comando: sirve desde tu terminal, Claude Code o Codex.

## Usarlo

```bash
echo "OPENROUTER_API_KEY=sk-or-v1-..." > .env     # en tu carpeta de trabajo
uvx --from git+https://github.com/zsoist/SWARMS enjambre "escribe la documentación de este proyecto"
uvx --from git+https://github.com/zsoist/SWARMS enjambre-visor    # localhost:8777
```

Lee `.env` y escribe `runs/<fecha>-swarm/` en la carpeta donde lo corres (o en
`ENJAMBRE_DIR`): cada entregable en `artifacts/`, el ensamblado en `FINAL.md`.

| Modo | Para qué |
|---|---|
| `enjambre "reto"` | el planificador arma el DAG de tareas |
| `enjambre --plan plan.json` | tú escribes el DAG (ver `ejemplos/plan_ejemplo.json`) |
| `enjambre --resume runs/<dir>` | retomar una corrida cortada |
| `enjambre --demo` | prueba de 1 minuto |
| `enjambre --help` | todo esto, con la flota que quedó configurada |

Desde un agente: pídele que corra el comando y que lea `FINAL.md`. Con
`--plan`, el agente que te atiende escribe el plan y el enjambre solo ejecuta.

## Con GLM (la flota por defecto), para que salga bien a la primera

| Regla | Por qué (medido el 2026-09-23) |
|---|---|
| `"thinking": "none"` en las tareas del plan | GLM no deja apagar el razonamiento; "none" pide effort low. Con "medium" 7 de 8 workers volvieron vacíos |
| `"ensamblar": false` si el entregable son los artefactos (JSON, código) | el ensamblado con el modelo grande tardaba 3 min y nadie leía `FINAL.md`; queda un índice |
| Mira la línea `flota:` del final | dice qué modelo contestó y cuántas respuestas vinieron vacías. Si no es GLM o hay vacías, algo cambió |
| `ENJAMBRE_OPENROUTER_KEY` si otra app usa la misma llave | el enjambre gasta de su llave; un día de enjambre le cerró el tope diario a un sitio público |
| Los proveedores cambian: re-mide con `ejemplos/banco_proveedores.mjs` | la ruta está en `AFINADO` de `enjambre/nucleo.py` |

```json
{"task": "…", "ensamblar": false,
 "tasks": [{"id": "a", "prompt": "…", "deps": [], "filename": "a.json", "thinking": "none"}]}
```

## Configuración (variables de entorno)

| Variable | Por defecto | Qué |
|---|---|---|
| `ENJAMBRE` | `glm` | `glm`: `z-ai/glm-5.3-flash` + `z-ai/glm-5.3` · `deepseek`: `deepseek-flash` + `deepseek-v4-pro` |
| `WORKER_MODEL` / `BRAIN_MODEL` | según la flota | cualquier modelo; con `/` va por OpenRouter |
| `ENJAMBRE_PARALELO` | `12` | agentes en paralelo (probado con 20; `MAX_DEEPSEEK_AGENTS` sigue valiendo) |
| `OPENROUTER_BUDGET_USD` / `DEEPSEEK_BUDGET_USD` | `10` / `10` | techo; al llegar se detiene solo |
| `OR_MAX_PROMPT` / `OR_MAX_COMPLETION` | `1.0` / `3.0` | techo de precio por millón de tokens |
| `JEV_MAX_CALLS` | `60` | llamadas al juez por corrida |
| `ENJAMBRE_OPENROUTER_KEY` | — | llave propia del enjambre; gana sobre `OPENROUTER_API_KEY` |
| `ENSAMBLAR` | `1` | `0` = no ensamblar (igual que `"ensamblar": false` en el plan) |
| `GLM_PROVIDERS` / `GLM_BRAIN_PROVIDERS` | medidos | orden de proveedores de la tropa y del cerebro |
| `GLM_MAX_TOKENS` / `GLM_BRAIN_MAX_TOKENS` | `24000` / `32000` | razonamiento + respuesta |
| `GLM_HEDGE_S` | `150` | segundos antes de lanzar la petición de cobertura |

Con la flota `glm` basta `OPENROUTER_API_KEY`. `DEEPSEEK_API_KEY` solo para `deepseek`.

## Lo que está cableado, y el número detrás

| Qué | Medido |
|---|---|
| Razonamiento explícito por modelo | GLM sin `effort` cuesta 3×, con `max` 7×. DeepSeek con `effort:"low"` devolvió 5/6 respuestas vacías; con `enabled:false`, 1/6 |
| GLM de tropa por defecto | 0% de respuestas vacías contra 17% de DeepSeek Flash (4 tareas × 3) |
| `require_parameters` | sin él, OpenRouter descarta en silencio lo que el proveedor no soporta |
| GLM: techo de 24k tokens | con effort low razona 5–12k tokens en tareas largas; con techo de 8.192 `content` volvía vacío (cobrado igual) |
| GLM tropa: CoreWeave, Parasail, Friendli, BaseTen; `sort: throughput` | CoreWeave 16–124 s, Parasail 40–81 s, Friendli 49–161 s; DeepInfra/Morph 677 s; Together contesta en 3 s sin razonar (lista vacía); Wafer razona hasta el techo sin contestar |
| GLM cerebro con ruta propia: Baidu, Io Net, Novita, Inceptron, InferenceNet | CoreWeave no sirve `glm-5.3` y los de la tropa cobran $4,40/M (fuera del techo de precio). Planes válidos en 24–28 s; Phala 154 s y error |
| Vacío = reintento con el mismo modelo y otro proveedor | antes el reintento iba fijo a `deepseek-flash`: pedías GLM y contestaba DeepSeek |
| Compuerta determinista: `.json` parsea, `.py` compila, `.js` pasa `node --check`, `.yaml` carga | el juez no mira código ni datos, pero nada lo verificaba: 2 de 9 JSON rotos se shippearon. Si falla, reintento con el error exacto; `.json` además pide modo JSON al proveedor |
| Cobertura (`GLM_HEDGE_S`, 150 s) y línea `llamadas:` | un worker en 336 s frenaba a 8 que terminaron en ≤91 s. Con cobertura y ruta medida: 9 workers en 138 s, 0 vacías, $0,057. El tiempo sigue al razonamiento (~110 tokens/s): 1.639 tokens → 22 s, 15.642 → 138 s |
| Juez solo en prosa | acierta 8/8 en prosa, 2/5 en código, 1/10 en lotes de parches, 0/7 verificando datos. Decide la extensión del archivo |
| Cercas de código fuera | los modelos envuelven el archivo en ```` ``` ```` aunque se les prohíba; sin quitarla, un `.js` no carga |
| Nombres repetidos | dos tareas con el mismo archivo se pisaban; ahora la segunda lleva el id delante |
| Paralelismo | 19,3 s por tarea con 1–2 tareas, 6,8 s con 10+; 33 tareas en 73 s |

No esperes caché de prefijo por OpenRouter: 0 tokens cacheados en todas las pruebas.

## Cuánto cuesta

`--demo` (5 entregables): 67 s, $0.0063. Cinco documentos largos: 153 s, $0.02.

## Si falla

| Síntoma | Causa |
|---|---|
| `⛔ falta OPENROUTER_API_KEY en …/.env` | no hay `.env` en la carpeta donde corres el comando |
| `flota: … ⚠️ N respuestas vacías` | el razonamiento se comió el techo en ese proveedor; se reintentó con otro. Si se repite, re-mide con `ejemplos/banco_proveedores.mjs` |
| una corrida de minutos por tarea | un proveedor lento en la ruta: re-mide y ajusta `GLM_PROVIDERS` |
| 429 | límite del proveedor: baja `ENJAMBRE_PARALELO` (la ruta ya cae a otro proveedor) |

## Pruebas

`uv run --with pytest pytest -q` — sin red; cubren lo que se rompió con GLM (reintentos a
DeepSeek, techo corto, rutas cruzadas, ensamblado, `--help`, llave propia). Corren en cada push.
