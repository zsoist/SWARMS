#!/usr/bin/env bash
# SWARMS installer for macOS and Linux (on Windows, use WSL).
#
#   curl -fsSL https://raw.githubusercontent.com/zsoist/SWARMS/main/instalar.sh | bash
#
# It does 5 things. You can run it again: each step is safe to repeat.
#   1. Installs uv (the Python tool manager) if it is missing.
#   2. Installs the `enjambre` command.
#   3. Keeps your DeepSeek key in ~/.enjambre.env (only you can read it).
#   4. Installs the `enjambre` skill for Claude Code and a short rule in ~/.claude/CLAUDE.md.
#   5. Sets Claude Code to Opus, if you did not set a model before.
# Then it makes one small test call to DeepSeek.
set -euo pipefail

REF="${ENJAMBRE_REF:-main}"
RAW="https://raw.githubusercontent.com/zsoist/SWARMS/$REF"
ZIP="https://github.com/zsoist/SWARMS/archive/refs/heads/$REF.zip"
ENV_FILE="$HOME/.enjambre.env"
CLAUDE_DIR="$HOME/.claude"

hay_tty() { ( exec < /dev/tty ) 2>/dev/null; }
paso() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# 1. uv
paso "1/5  uv"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

# 2. enjambre command
paso "2/5  enjambre command"
uv tool install --force --reinstall --quiet "enjambre @ $ZIP"
uv tool update-shell >/dev/null 2>&1 || true
export PATH="$(uv tool dir --bin):$PATH"
command -v enjambre

# 3. DeepSeek key
paso "3/5  DeepSeek key"
tiene_llave() { [ -f "$ENV_FILE" ] && grep -Eq '^(export )?DEEPSEEK_API_KEY=.+' "$ENV_FILE"; }

pedir_llave() {   # $1 = text for the prompt
  if ! hay_tty; then
    echo "⛔ No terminal to ask for the key. Run the install line in the Terminal app,"
    echo "   or put the key in front of it:  DEEPSEEK_API_KEY=sk-... bash -c \"\$(curl -fsSL $RAW/instalar.sh)\""
    exit 1
  fi
  printf '%s' "$1"
  read -rs KEY < /dev/tty
  echo
}

guardar_llave() {
  case "$KEY" in
    sk-*) ;;
    *) echo "⛔ That is not a DeepSeek key (it must start with sk-). Run the installer again."; exit 1 ;;
  esac
  ( umask 077
    if [ -f "$ENV_FILE" ]; then
      # Keep the other settings. Replace only the key line.
      grep -Ev '^(export )?DEEPSEEK_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
      printf 'DEEPSEEK_API_KEY=%s\n' "$KEY" >> "$ENV_FILE.tmp"
      # This kit is for DeepSeek: set the fleet if the file does not say it.
      grep -Eq '^(export )?ENJAMBRE=' "$ENV_FILE.tmp" || echo 'ENJAMBRE=deepseek' >> "$ENV_FILE.tmp"
      mv "$ENV_FILE.tmp" "$ENV_FILE"
    else
      cat > "$ENV_FILE" <<EOF
# enjambre settings. Only you can read this file. Never put it in git.
DEEPSEEK_API_KEY=$KEY
ENJAMBRE=deepseek
# Stop a run when it costs more than this (USD).
DEEPSEEK_BUDGET_USD=5
# Workers that run at the same time.
ENJAMBRE_PARALELO=12
EOF
    fi
    chmod 600 "$ENV_FILE"
  )
  echo "Key saved in $ENV_FILE."
}

KEY="${DEEPSEEK_API_KEY:-}"
if [ -n "$KEY" ]; then
  guardar_llave
elif tiene_llave; then
  echo "Key found in $ENV_FILE."
  if hay_tty; then
    pedir_llave 'Paste a new key to replace it, or push Enter to keep it: '
    [ -n "$KEY" ] && guardar_llave
  fi
else
  pedir_llave 'Paste your DeepSeek API key (the text does not show) and push Enter: '
  guardar_llave
fi

# 4. Claude Code skill and global rule
paso "4/5  Claude Code skill"
mkdir -p "$CLAUDE_DIR/skills/enjambre"
curl -fsSL "$RAW/kit/skills/enjambre/SKILL.md" -o "$CLAUDE_DIR/skills/enjambre/SKILL.md"
echo "Skill: $CLAUDE_DIR/skills/enjambre/SKILL.md"
BLOQUE="$(curl -fsSL "$RAW/kit/CLAUDE.global.md")"
touch "$CLAUDE_DIR/CLAUDE.md"
# Remove the old block (if there is one), then add the new block.
awk '/<!-- enjambre:start -->/{s=1} !s{print} /<!-- enjambre:end -->/{s=0}' \
  "$CLAUDE_DIR/CLAUDE.md" > "$CLAUDE_DIR/CLAUDE.md.tmp"
printf '%s\n' "$BLOQUE" >> "$CLAUDE_DIR/CLAUDE.md.tmp"
mv "$CLAUDE_DIR/CLAUDE.md.tmp" "$CLAUDE_DIR/CLAUDE.md"
echo "Rule: $CLAUDE_DIR/CLAUDE.md"

# 5. Opus as the default model (only if no model is set)
# Opus 5.5 uses medium effort by default. The old top-level "effortLevel" key does
# not apply to it, so we do not write it.
paso "5/5  Claude Code model"
uv run --quiet --no-project python - "$CLAUDE_DIR/settings.json" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
try:
    s = json.loads(p.read_text()) if p.exists() else {}
except json.JSONDecodeError:
    print(f"{p} is not valid JSON. No change. Select Opus in the model menu of Claude.")
    sys.exit(0)
if "model" in s:
    print(f"Model already set in {p}: {s['model']}. No change.")
else:
    s["model"] = "opus"
    p.write_text(json.dumps(s, indent=2) + "\n")
    print(f"Set in {p}: model = opus")
PY

# Test
paso "Test: one small call to DeepSeek"
if ! enjambre --check; then
  echo "⛔ The test call failed. Usual causes: a wrong key, or no balance at https://platform.deepseek.com"
  if hay_tty; then
    pedir_llave 'Paste the key again (or push Enter to stop): '
    [ -z "$KEY" ] && exit 1
    guardar_llave
    enjambre --check || { echo "⛔ It failed again. Check the key and the balance, then run the installer again."; exit 1; }
  else
    exit 1
  fi
fi

cat <<'EOF'

✅ Ready.
   1. Quit Claude completely and open it again (Desktop app or terminal).
      Claude reads the new skill only when it starts.
   2. Open a project folder. Ask for a feature. For heavy work, Claude uses the swarm.
   3. To force it, write: "use the enjambre skill".
   Guide: https://github.com/zsoist/SWARMS/blob/main/START.md
EOF
