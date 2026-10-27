<!-- enjambre:start -->
## Token budget: Opus plans, the DeepSeek swarm writes

- I use Claude Pro. Opus tokens are limited. Keep your own output short.
- For heavy work (3 or more new files, or more than about 150 new lines), use the `enjambre` skill.
  You write the plan and check the result. The swarm writes the code.
- Do small edits and debugging yourself. Make a plan before a change to more than 3 files.
- Send long command output through `tail`. Read only the lines that you need.
- Never send secrets (`.env` values, keys, tokens) to the swarm or to the chat.

## Safety: Supabase and Vercel

- Enable RLS and write its policies in the same migration that creates a table.
- Use only the Supabase publishable key in browser code. Never give the secret key a `NEXT_PUBLIC_` prefix.
- Show each SQL migration to me. Apply it to dev first, and to prod only after I say yes.
- Never drop, reset, or bulk-delete prod data without a backup and a clear yes from me.
- Put `.env` and `.env*.local` in `.gitignore` before the first commit. After you change a Vercel env var, redeploy.
<!-- enjambre:end -->
