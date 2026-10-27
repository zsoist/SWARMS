# SWARMS — enjambre

One model plans. Many cheap models write in parallel. A cheap judge checks.
It is one command. You can use it from a terminal, from Claude Code, or from Codex.

**Main use:** Claude Code on Opus plans the work, and a DeepSeek swarm writes the code.
Opus tokens go to decisions. DeepSeek tokens go to volume. A Claude Pro plan lasts much longer.

## Install (macOS, Linux, WSL)

You need a DeepSeek API key from <https://platform.deepseek.com>.

```bash
curl -fsSL https://raw.githubusercontent.com/zsoist/SWARMS/main/instalar.sh | bash
```

The installer:

1. Installs `uv` if it is missing.
2. Installs the `enjambre` command.
3. Keeps your key in `~/.enjambre.env` (mode 600, only you can read it).
4. Installs the `enjambre` skill in `~/.claude/skills/` and a short rule in `~/.claude/CLAUDE.md`.
5. Sets Claude Code to Opus with medium effort, if no model is set.
6. Makes one test call (`enjambre --check`).

You can run it again. Each step is safe to repeat. Step-by-step guide for a new user: [`START.md`](START.md).

## How it works

```
You ──▶ Claude Code (Opus)                 plans, checks, connects the parts
            │ writes .enjambre/plan.json
            ▼
        enjambre --plan                    DeepSeek workers, up to 12 at the same time
            │ writes runs/<date>-swarm/artifacts/
            ▼
        Claude Code copies the files (cp), runs tsc / build, fixes small errors
```

The skill [`kit/skills/enjambre/SKILL.md`](kit/skills/enjambre/SKILL.md) tells Claude when to use the swarm and how to write the plan.

## Commands

| Command | What it does |
|---|---|
| `enjambre "task"` | The brain model makes the plan (a DAG of tasks), then the workers do it. |
| `enjambre --plan plan.json` | You (or your agent) write the plan. The workers only do it. |
| `enjambre --resume runs/<dir>` | Continue a run that stopped. |
| `enjambre --demo` | A one-minute test. |
| `enjambre --check` | One small call. It confirms the key and the fleet. |
| `enjambre --help` | All of this, with the fleet that is set now. |
| `enjambre-visor` | A dashboard on `localhost:8777`. |

The command reads `.env` in the current folder, then `~/.enjambre.env`.
It writes `runs/<date>-swarm/` in the current folder (or in `ENJAMBRE_DIR`).
Each result is in `artifacts/`. `FINAL.md` has the assembled result or an index.

## Plan format

```json
{"task": "…", "ensamblar": false,
 "tasks": [{"id": "a", "prompt": "…", "deps": [], "filename": "a.ts",
            "thinking": "none", "archivos": ["src/lib/db.ts"]}]}
```

| Field | Meaning |
|---|---|
| `filename` | One file name with its extension. The extension sets the checks. |
| `deps` | Tasks whose result this task needs. A task without `deps` starts at once. |
| `thinking` | `none` (mechanical), `low`, `medium`, `high`. More thinking costs more. |
| `archivos` | Project files that the worker must see. The swarm reads them from disk. |
| `ensamblar` | `false` when the result is code or data. No assembly step: faster and cheaper. |

## Fleets

| `ENJAMBRE` | Workers | Brain | Key |
|---|---|---|---|
| `deepseek` | `deepseek-flash` | `deepseek-v4-pro` | `DEEPSEEK_API_KEY` |
| `glm` | `z-ai/glm-5.3-flash` | `z-ai/glm-5.3` | `OPENROUTER_API_KEY` |

If you do not set `ENJAMBRE`: with only a DeepSeek key, the fleet is `deepseek`. In all other cases it is `glm`.
DeepSeek runs on its own API. If it fails and an OpenRouter key exists, the call goes to OpenRouter and the output says so.

## Settings (environment variables)

| Variable | Default | What |
|---|---|---|
| `ENJAMBRE` | see above | `deepseek` or `glm` |
| `WORKER_MODEL` / `BRAIN_MODEL` | from the fleet | Any model. A name with `/` goes to OpenRouter. |
| `ENJAMBRE_PARALELO` | `12` | Workers at the same time (tested with 20). `MAX_DEEPSEEK_AGENTS` also works. |
| `DEEPSEEK_BUDGET_USD` / `OPENROUTER_BUDGET_USD` | `10` / `10` | Spend limit for each run. The run stops at the limit. |
| `OR_MAX_PROMPT` / `OR_MAX_COMPLETION` | `1.0` / `3.0` | Price limit per million tokens (OpenRouter). |
| `JEV_MAX_CALLS` | `60` | Judge calls for each run. The judge needs an OpenRouter key. |
| `ENJAMBRE_OPENROUTER_KEY` | — | The swarm's own OpenRouter key. It wins over `OPENROUTER_API_KEY`. |
| `ENSAMBLAR` | `1` | `0` = no assembly (same as `"ensamblar": false`). |
| `GLM_PROVIDERS` / `GLM_BRAIN_PROVIDERS` | measured | Provider order for GLM workers and brain. |
| `GLM_MAX_TOKENS` / `GLM_BRAIN_MAX_TOKENS` | `24000` / `32000` | Reasoning plus answer, for GLM. |
| `GLM_HEDGE_S` | `150` | Seconds before a second (hedge) request to GLM. |
| `DEEPSEEK_MAX_TOKENS` / `DEEPSEEK_MAX_TOKENS_RAZONANDO` | `32000` / `64000` | Output limit for DeepSeek, without and with thinking. The API default is 8K without thinking. |
| `DEEPSEEK_TIMEOUT_S` | `900` | Wait limit for one DeepSeek call. |

## Measured facts behind the code

| Rule | Measurement |
|---|---|
| DeepSeek: thinking off is `thinking: {type: disabled}` | The API turns thinking on (`high`) when you say nothing: 26 reasoning tokens for "Say ok". With `disabled`: 0. |
| No silent fallback to OpenRouter | Before, any DeepSeek error sent the call to OpenRouter with no message. Without an OpenRouter key, that hid the real error behind a second one. |
| DeepSeek JSON mode needs the word "json" in the prompt | Without it, the API returns 400 (measured 2026-10-27). The swarm adds the word when it is missing. |
| DeepSeek: explicit `max_tokens`; `finish_reason` `length` is a failure | The default is 8K without thinking, so a long file was cut and passed as good. Now a cut answer is recorded and tried again with a higher limit. Measured: a 700-line file is 4,150 tokens (15 s) without thinking; 29,189 tokens, 18,251 of them thinking (127 s), with `high`. |
| DeepSeek 401/402 stops the run; 400/422 never go to OpenRouter | A wrong key or no balance failed each task one by one. A bad request fails the same way on OpenRouter. |
| DeepSeek cost uses peak prices and the cache | Peak (01–04 and 06–10 UTC, Mon–Fri) is 2× off-peak. With old prices the budget limit was passed 2×. |
| Thinking is set for each model | GLM with no `effort` costs 3×, with `max` 7×. DeepSeek with `effort: "low"` returned 5 of 6 empty answers; with thinking off, 1 of 6. |
| An empty answer is never hidden | It goes to the `flota:` line and the swarm tries again with the same model (DeepSeek: with thinking off; GLM: on a different provider). |
| `require_parameters` (OpenRouter) | Without it, OpenRouter drops parameters that the provider does not support, and it does not tell you. |
| GLM: 24k token limit for workers | With effort low, GLM thinks 5–12k tokens on long tasks. With a limit of 8,192 the answer was empty, and it was billed. |
| GLM workers: CoreWeave, Parasail, Friendli, BaseTen; `sort: throughput` | CoreWeave 16–124 s, Parasail 40–81 s, Friendli 49–161 s. DeepInfra/Morph 677 s. Together answers in 3 s with no reasoning (empty list). Wafer thinks to the limit and gives no answer. |
| GLM brain has its own route | CoreWeave does not serve `glm-5.3`. The worker providers charge $4.40/M (above the price limit). Valid plans in 24–28 s. |
| Runaway reasoning (`fin=length`) → the retry limits `reasoning.max_tokens` (`GLM_RAZON_REINTENTO`, 8000) | With effort low, GLM thought 24,000 tokens and gave no answer. A higher limit only gave it more room. |
| Machine checks: `.json` parses, `.py` compiles, `.js` passes `node --check`, `.yaml` loads | The judge does not check code or data. Before this check, 2 of 9 broken JSON files shipped. On failure, the retry gets the exact error. `.json` also asks the provider for JSON mode. |
| Hedge request (`GLM_HEDGE_S`, 150 s) and the `llamadas:` line | One worker took 336 s while 8 finished in 91 s or less. With the hedge and a measured route: 9 workers in 138 s, 0 empty, $0.057. |
| Judge only for prose | Correct 8/8 on prose, 2/5 on code, 1/10 on patch batches, 0/7 on data checks. The file extension decides. |
| Code fences are removed | Models wrap the file in ```` ``` ```` also when told not to. With the fence, a `.js` file does not load. |
| Same file name twice | The second task gets its id in front of the name. Before, the second file replaced the first. |
| Parallel work | 19.3 s per task with 1–2 tasks, 6.8 s with 10 or more. 33 tasks in 73 s. |

Do not expect prefix cache through OpenRouter: 0 cached tokens in all tests. DeepSeek's own API caches the prefix automatically.

## Cost

`--demo` (5 results): 67 s, $0.0063. Five long documents: 153 s, $0.02.

## Problems

| Output | Cause | Action |
|---|---|---|
| `⛔ falta DEEPSEEK_API_KEY …` | No key in `.env` or `~/.enjambre.env`. | Run the installer again. |
| `command not found: enjambre` | The tool folder is not on the PATH. | Run `uv tool update-shell`, then open a new terminal. |
| `flota: … ⚠️ N respuestas vacías` | Reasoning used all the tokens. The swarm tried again. | No action if the files are there. If it repeats with GLM, measure again with `ejemplos/banco_proveedores.mjs`. |
| `💸 Techo de … alcanzado` | The run reached its budget. | Increase `DEEPSEEK_BUDGET_USD` if this is correct. |
| `401` or `402` from DeepSeek | Wrong key, or no balance. | Check <https://platform.deepseek.com>. |
| `429` | Provider rate limit. | Decrease `ENJAMBRE_PARALELO`. |

## Tests

```bash
uv run --with pytest pytest -q
```

No network. The tests cover each bug that already happened (see `CLAUDE.md`). CI runs them on each push.
