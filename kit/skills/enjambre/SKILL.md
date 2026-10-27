---
name: enjambre
description: Send heavy work to a cheap DeepSeek swarm. Use it when a task makes 3 or more new files or more than about 150 lines - for example pages, components, API routes, Supabase SQL migrations, seed data, tests, docs, or research drafts. You plan and review; the swarm writes. Do not use it for small edits, one-line fixes, or debugging.
---

# enjambre: you plan, the swarm writes

## Why

You run on Opus with a Claude Pro plan. Opus tokens are expensive and the plan limit is small.
The swarm runs on DeepSeek. It costs cents for work that costs Opus a large part of the limit.

Your job: plan, run the swarm, check, and connect the parts.
The swarm's job: write the large text and the code.

## When to use the swarm

Use the swarm for:

- 3 or more new files.
- One file with more than about 150 new lines.
- Repeated work: many similar components, routes, tests, or translations.
- Drafts: docs, README, SQL migrations, seed data, copy text.

Do the work yourself for:

- Edits of less than about 50 lines.
- Debugging. The swarm cannot run the code.
- Work that needs many project files to understand.
- Secrets. Never put keys, tokens, or `.env` values in a plan. The plan goes to DeepSeek.

## Procedure

1. Read only the files that you need to make the plan.
2. Make sure that `.gitignore` contains `runs/` and `.enjambre/`. Add them if they are missing.
3. Write the plan to `.enjambre/plan.json` (format below).
4. Run the swarm from the project root. Set the Bash timeout to 600000 ms:

   ```bash
   enjambre --plan .enjambre/plan.json
   ```

5. Read only the end of the output. It shows the path of each file and a `flota:` line.
6. Copy each file to its place with `cp`. Do not read a file and write it again: that costs Opus tokens.

   ```bash
   cp runs/<run>/artifacts/Card.tsx src/components/Card.tsx
   ```

7. Check the result with the project tools, for example `npx tsc --noEmit`, `npm run lint`, or `npm run build`.
8. Fix small errors yourself. For a large error, run the swarm again for that one task. Put the exact error in the prompt.
9. Tell the user the cost. The output shows it (for example `deepseek $0.0123`).

## Plan format

```json
{
  "task": "Pricing page and API for the app",
  "ensamblar": false,
  "tasks": [
    {
      "id": "types",
      "filename": "pricing.ts",
      "thinking": "none",
      "archivos": ["src/lib/supabase.ts"],
      "prompt": "Write src/lib/pricing.ts in TypeScript. Export type Plan = {id: string; name: string; priceCents: number}. Export async function getPlans(): Promise<Plan[]> that reads table 'plans' with the Supabase client from src/lib/supabase.ts. Return only the file."
    },
    {
      "id": "page",
      "filename": "page.tsx",
      "thinking": "low",
      "deps": ["types"],
      "archivos": ["src/app/layout.tsx"],
      "prompt": "Write src/app/pricing/page.tsx for Next.js App Router. It is a server component. It calls getPlans() from '@/lib/pricing' and shows one card per plan with Tailwind. Return only the file."
    }
  ]
}
```

### Rules for the plan

- **One file for each task.** `filename` is only a file name, with the correct extension. The swarm does not make folders.
- **Make each prompt complete.** A worker does not see the project. It sees only its prompt, its `archivos`, and the first 2000 characters of each task in `deps`.
- **Use `archivos` for context.** List the project files that the worker must see. The swarm reads them from disk. Do not paste file contents into the prompt: that costs Opus tokens.
- **Give exact names.** Write the path, the exports, the types, the table names, and the libraries in the prompt.
- **Add `deps` only for real inputs.** Tasks without `deps` run at the same time (up to 12).
- **Set `thinking` for each task:**
  - `"none"`: mechanical work (most tasks).
  - `"low"`: normal logic.
  - `"high"`: hard logic, for example auth rules or money calculations.
- **Set `"ensamblar": false`** when the result is code or data. It is faster and cheaper.
- **Tell the worker to return only the file.** The swarm removes code fences, but clear output is better.

## What the swarm checks

- `.json` must parse. `.py` must compile. `.js` and `.mjs` must pass `node --check`. `.yaml` must load.
- If a check fails, the swarm sends the exact error back to the worker one more time.
- `.ts`, `.tsx`, `.sql`, and `.css` are **not** checked. You must check them (step 7).

## Supabase and Vercel

- **SQL migrations:** the swarm writes the SQL. You read it before you apply it. Apply it with the Supabase connector or with `supabase db push`. Always enable Row Level Security on new tables.
- **Deploy:** Vercel deploys on `git push` when the repo is connected. You can also use the Vercel connector or `vercel deploy`.
- **Environment variables:** keep them in `.env.local` and in the Vercel project settings. Never put them in a plan.

## If something fails

| Output | Cause | Action |
|---|---|---|
| `⛔ falta DEEPSEEK_API_KEY` | No key in `~/.enjambre.env` | Tell the user to run the installer again. |
| `command not found: enjambre` | The tool is not on the PATH | Run `uv tool update-shell` and open a new terminal. |
| `flota: ... ⚠️ N respuestas vacías` | DeepSeek returned empty text; the swarm tried again | No action if the files are there. |
| `💸 Techo de deepseek alcanzado` | The run reached the budget limit | Tell the user. The limit is `DEEPSEEK_BUDGET_USD` in `~/.enjambre.env`. |
| A file is bad | The prompt was not clear | Run that task again with a more exact prompt. |

To test the key and the connection with one small call: `enjambre --check`.
