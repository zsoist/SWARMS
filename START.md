# START: Claude Pro + DeepSeek swarm + Supabase + Vercel

This guide is for a new user. Time: about 10 minutes.

**Result:** Claude (Opus) plans your app and checks the work. A DeepSeek swarm writes most of the code for cents.
Your Claude Pro limit lasts much longer.

## What you need

| Item | Where |
|---|---|
| Claude Pro plan | <https://claude.ai> |
| Claude Desktop app | <https://claude.ai/download> |
| DeepSeek API key | You get it from the person who sent this guide, or from <https://platform.deepseek.com> → API keys |
| Vercel account | <https://vercel.com> |
| Supabase account | <https://supabase.com> |
| GitHub account | <https://github.com> (Vercel deploys from GitHub) |
| A Mac, Linux, or Windows with WSL | |

## Step 1: Install the swarm

1. Open the Terminal app.
2. Copy this line, paste it, and push Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/zsoist/SWARMS/main/instalar.sh | bash
   ```

3. When it asks, paste the DeepSeek key and push Enter. The key does not show. This is correct.
4. At the end you see `✅ deepseek-flash → 'ok'` and `✅ Ready.`

If you see `⛔`, read the line under it. Most of the time the key is wrong or the DeepSeek account has no balance.

## Step 2: Connect Supabase and Vercel to Claude

1. Open Claude Desktop.
2. Go to **Settings → Connectors**.
3. Add **Supabase**. Sign in and allow access.
4. Add **Vercel**. Sign in and allow access.

Now Claude can make database tables, read logs, and see deploys.

## Step 3: Set the model

The installer sets Opus with medium effort for Claude Code. To change it, open the model menu in the Code tab:

- **Opus, effort low or medium**: the default for this setup. Opus plans, the swarm writes.
- Use **high** effort only for a hard problem. It uses the Pro limit fast.

## Step 4: Make an app

1. In Claude Desktop, open the **Code** tab.
2. Select a folder for the project (a new empty folder is good).
3. Paste this first message, and change the idea:

   ```text
   Make a Next.js app with Supabase (auth and database) and deploy it on Vercel.
   The idea: <describe your app here>.
   Plan first. Use the enjambre skill for the heavy work.
   Ask me before you make a Supabase project or a Vercel project.
   ```

Claude makes a plan, sends the large work to the swarm, checks the result, and deploys.
After each swarm run, Claude shows the cost (for example `deepseek $0.02`).

## Good habits

- Ask for one feature at a time. Small steps are cheaper and easier to check.
- For heavy work, write "use the enjambre skill". Claude then sends it to the swarm.
- Keep secrets in `.env.local` and in Vercel → Project → Settings → Environment Variables. Never paste them in the chat.
- Look at your DeepSeek balance sometimes: <https://platform.deepseek.com/usage>.
- When Claude says that you are near the Pro limit, stop and continue later. The limit resets every 5 hours.

## Change or remove

| To | Do this |
|---|---|
| Change the DeepSeek key | Edit `~/.enjambre.env`, then run `enjambre --check`. |
| Change the spend limit for each run | Edit `DEEPSEEK_BUDGET_USD` in `~/.enjambre.env`. |
| Update the swarm | Run the install line from step 1 again. |
| Remove the swarm | `uv tool uninstall enjambre`, then delete `~/.enjambre.env` and `~/.claude/skills/enjambre`. |
