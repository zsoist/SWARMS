# CLAUDE.md — SWARMS (enjambre)

One brain plans. A cheap fleet writes in parallel. A judge checks.
All the core is in `enjambre/nucleo.py`. Use and numbers: `README.md`. New-user guide: `START.md`.

## Commands

```bash
uv run --with pytest pytest -q                       # before each push (no network)
uv run enjambre --help
uv run enjambre --check                              # one real call: key and fleet
node ejemplos/banco_proveedores.mjs <model> <prompt.txt> <prov...>   # measure routes again
```

## Files

| Path | What |
|---|---|
| `enjambre/nucleo.py` | Fleets, model calls, plan, workers, checks, CLI. |
| `kit/skills/enjambre/SKILL.md` | The skill that tells Claude Code when and how to use the swarm. The installer copies it. |
| `kit/CLAUDE.global.md` | The short rule that the installer adds to `~/.claude/CLAUDE.md`. |
| `instalar.sh` | One-command installer. It downloads the files above from `main`. |
| `tests/test_glm.py` | Tests without network. One test for each bug that happened. |

## Rules. Each rule comes from a real failure.

- **The fleet that you ask for must answer.** No fixed model names in the code: retries use `WORKER_MODEL`.
  A fixed `"deepseek-flash"` sent 16 of 17 "GLM" answers to DeepSeek, and nobody saw it.
- **DeepSeek native: turn thinking off on purpose.** With no setting, thinking is on (`high`) and costs output tokens.
  We send `thinking: {type: disabled}` (measured 2026-10-27: 0 reasoning tokens; `reasoning_effort: "none"` also works).
- **No silent fallback.** DeepSeek goes to OpenRouter only when an OpenRouter key exists, and the output says so.
  Without that key, show the real DeepSeek error.
- **DeepSeek JSON mode needs the word "json" in the prompt.** Without it: 400. `llm()` adds it.
- **A cut answer is a failure.** Set `max_tokens` (DeepSeek default: 8K without thinking).
  `finish_reason` `length`, `insufficient_system_resource`, or `aborted` → record in `VACIOS` and retry with more.
- **Stop the run on 401/402** (wrong key, no balance). Never send 400/422 to OpenRouter: they fail there too.
- **High token limit for GLM** (it thinks also with effort low): 24k for workers, 32k for the brain.
  With 8,192 the `content` came back empty, and it was billed.
- **Workers and brain have different routes** (`AFINADO`, the longest key wins).
  The large model has different providers and different prices.
- **Never hide an empty answer.** Record it in `VACIOS`. It shows in the `flota:` line.
  Retry with the same model (GLM: on a different provider; DeepSeek: with thinking off).
- **Routes come from measurement, not from brand.** Providers change each week.
  Before you change `order`/`ignore`, measure with `ejemplos/banco_proveedores.mjs`.
- **The swarm has its own key** (`ENJAMBRE_OPENROUTER_KEY`). A shared key closed the daily limit of a public app.
- **Secrets only in `.env` or `~/.enjambre.env`.** This repo is public.
- **The installer must be safe to run again.** Each step checks before it changes a file.
  It never replaces a user's key or model setting.
- **Each fix comes with a test in `tests/`.** The test fails with the bug and passes without it.

## Docs style

Write docs in Simplified Technical English (ASD-STE100 style): short sentences, active voice,
one instruction for each sentence, one meaning for each word. Humans and LLMs must both read them easily.
Code comments stay in Spanish, like the code.
