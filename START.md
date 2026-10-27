# START: Claude Pro + DeepSeek swarm + Supabase + Vercel

This guide is for a new user. Time: about 15 minutes.

**Result:** Claude (Opus) plans your app and checks the work. A DeepSeek swarm writes most of the code for cents.
Your Claude Pro limit lasts much longer.

## What you need

| Item | Where |
|---|---|
| Claude Pro plan | <https://claude.ai> |
| Claude Desktop app | <https://claude.ai/download> |
| DeepSeek API key | From the person who sent this guide, or <https://platform.deepseek.com> → API keys |
| GitHub account | <https://github.com> (Vercel deploys from GitHub) |
| Vercel account | <https://vercel.com> (sign in with GitHub) |
| Supabase account | <https://supabase.com> (sign in with GitHub) |
| A Mac, Linux, or Windows with WSL | |

## Step 1: Install the swarm

1. Open the Terminal app.
2. Copy this line, paste it, and push Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/zsoist/SWARMS/main/instalar.sh | bash
   ```

3. When it asks, paste the DeepSeek key and push Enter. The key does not show. This is correct.
4. At the end you see `✅ deepseek-flash → 'ok'` and `✅ Ready.`
5. **Quit Claude Desktop completely (Cmd+Q) and open it again.** Claude reads the new skill only when it starts.

If you see `⛔`, read the line under it. Most of the time the key is wrong or the DeepSeek account has no balance.

## Step 2: Make two Supabase projects

An AI agent can make mistakes. Keep it away from the data of real users.

1. In Supabase, make a project `myapp-dev`. Claude works here.
2. Later, before real users come, make `myapp-prod`.

## Step 3: Connect Supabase and Vercel to Claude

1. In Claude Desktop, go to **Settings → Connectors**.
2. Add **Supabase**. Sign in. If it asks for a project, give access to `myapp-dev` only.
3. Add **Vercel**. Sign in.
4. Keep "ask before each action" on. Never select "always allow" for database changes.

## Step 4: The model

The installer sets **Opus**. Opus plans and checks. The swarm writes.

- Opus uses the Pro limit several times faster than Sonnet. The swarm is what makes Opus possible on Pro.
- Keep effort at **medium** (the default). Use `/effort low` for easy work. Avoid **high**.
- If you reach the limit too often, tell Claude: "set model to opusplan in ~/.claude/settings.json".
  Then Opus plans in Plan mode, and Sonnet does the steps. This uses much less of the limit.

## Step 5: Make an app

1. Make a **new empty folder** for the project, for example `~/Code/myapp`. Never use your home folder.
2. In Claude Desktop, open the **Code** tab and select that folder.
3. Set the permission selector to **Accept edits**. Then Claude does not ask for each file. Do not use "Bypass".
4. Paste this first message, and change the idea:

   ```text
   Make a Next.js app with Supabase (auth and database) and deploy it on Vercel.
   The idea: <describe your app here>.
   Start with git init. Make a plan first and show it to me.
   Use the enjambre skill for the heavy work.
   Use the Supabase project myapp-dev.
   Ask me before you make a Vercel project or change a database.
   ```

Claude makes a plan, sends the large work to the swarm, checks the result, and deploys.
After each swarm run, Claude shows the cost (for example `deepseek $0.02`).

## Good habits

**To save the Pro limit:**

- Ask for one feature at a time. Small steps are cheaper and easier to check.
- Type `/clear` when you start a different feature. Old conversation costs tokens on each message.
- When Claude goes in the wrong direction, push **Esc** at once. Use `/rewind` to go back.
- Give file paths (`src/app/page.tsx`). Do not paste whole files or long logs. For an error, paste only the last 20–30 lines.
- Write "use the enjambre skill" when you want the swarm. Claude does not always select it alone.
- Look at the usage ring in Claude Desktop (or type `/usage`). There is a 5-hour limit and a weekly limit.

**To keep the app safe:**

- Keep secrets in `.env.local` and in Vercel → Project → Settings → Environment Variables. Never paste them in the chat.
- Every Supabase table must have Row Level Security (RLS). Before each launch, open Supabase → Advisors → Security Advisor. Fix each red item.
- In Supabase → Authentication → URL Configuration, set **Site URL** to your Vercel URL. Without this, sign-in emails link to `localhost`.

**To avoid losing data or money:**

- The Supabase free plan has **no backups**. Each week, ask Claude to run `supabase db dump > backup.sql`.
- A free Supabase project **pauses after 7 days** with no use. Open the app each week, or restore it in the Supabase dashboard.
- The Vercel Hobby plan is free and stops at its limits. It is for personal projects only. For an app that earns money, use Pro, and set a budget in Settings → Billing → Spend Management with **Pause Production Deployments** on.
- Look at your DeepSeek balance sometimes: <https://platform.deepseek.com/usage>. Each swarm run stops at $5 (you can change this).

**About DeepSeek:** DeepSeek processes data on servers in China. Do not send it personal data of users or company secrets.

## Change or remove

| To | Do this |
|---|---|
| Change the DeepSeek key | Edit `~/.enjambre.env`, then run `enjambre --check`. |
| Change the spend limit for each run | Edit `DEEPSEEK_BUDGET_USD` in `~/.enjambre.env`. |
| Update the swarm | Run the install line from step 1 again. |
| Remove the swarm | `uv tool uninstall enjambre`, then delete `~/.enjambre.env` and `~/.claude/skills/enjambre`. |

## Problems

| You see | Do this |
|---|---|
| `⛔ DeepSeek 401` | The key is wrong. Edit `~/.enjambre.env`. |
| `⛔ DeepSeek 402` | No balance. Add balance at <https://platform.deepseek.com>. |
| Claude does not use the swarm | Write "use the enjambre skill". If it says it does not know the skill, quit Claude (Cmd+Q) and open it again. |
| `command not found: enjambre` | Tell Claude: "use ~/.local/bin/enjambre". |
| Claude asks permission for each step | Set the selector to **Accept edits**. |
| You reached the Pro limit | Wait for the reset (the usage ring shows when), or switch to `opusplan`. |
