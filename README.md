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

Desde un agente: pídele que corra el comando y que lea `FINAL.md`. Con
`--plan`, el agente que te atiende escribe el plan y el enjambre solo ejecuta.

## Configuración (variables de entorno)

| Variable | Por defecto | Qué |
|---|---|---|
| `ENJAMBRE` | `glm` | `glm`: `z-ai/glm-5.3-flash` + `z-ai/glm-5.3` · `deepseek`: `deepseek-flash` + `deepseek-v4-pro` |
| `WORKER_MODEL` / `BRAIN_MODEL` | según la flota | cualquier modelo; con `/` va por OpenRouter |
| `MAX_DEEPSEEK_AGENTS` | `8` | agentes en paralelo (probado con 20) |
| `OPENROUTER_BUDGET_USD` / `DEEPSEEK_BUDGET_USD` | `10` / `10` | techo; al llegar se detiene solo |
| `OR_MAX_PROMPT` / `OR_MAX_COMPLETION` | `1.0` / `3.0` | techo de precio por millón de tokens |
| `JEV_MAX_CALLS` | `60` | llamadas al juez por corrida |

Con la flota `glm` basta `OPENROUTER_API_KEY`. `DEEPSEEK_API_KEY` solo para `deepseek`.

## Lo que está cableado, y el número detrás

| Qué | Medido |
|---|---|
| Razonamiento explícito por modelo | GLM sin `effort` cuesta 3×, con `max` 7×. DeepSeek con `effort:"low"` devolvió 5/6 respuestas vacías; con `enabled:false`, 1/6 |
| GLM de tropa por defecto | 0% de respuestas vacías contra 17% de DeepSeek Flash (4 tareas × 3) |
| `require_parameters` | sin él, OpenRouter descarta en silencio lo que el proveedor no soporta |
| `sort: latency` | no cambia el precio (±3%); cambia la cola: p_max 1.582 ms contra 3.378 (price) y 14.396 (throughput) |
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
| respuestas vacías | el razonamiento se comió `max_tokens`: revisa el `reasoning` del modelo |
| 429 | límite del proveedor: baja `MAX_DEEPSEEK_AGENTS` |
