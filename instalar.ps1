# SWARMS installer for Windows (PowerShell 5.1 or 7).
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/zsoist/SWARMS/main/instalar.ps1 | iex"
#
# It does 6 things. You can run it again: each step is safe to repeat.
#   1. Installs uv (the Python tool manager) if it is missing.
#   2. Installs Git for Windows if it is missing (Claude Code uses its Bash).
#   3. Installs the `enjambre` command.
#   4. Keeps your DeepSeek key in %USERPROFILE%\.enjambre.env.
#   5. Installs the `enjambre` skill for Claude Code and a short rule in %USERPROFILE%\.claude\CLAUDE.md.
#   6. Sets Claude Code to Opus, if you did not set a model before.
# Then it makes one small test call to DeepSeek.
# This file is ASCII only: Windows PowerShell 5.1 reads scripts as ANSI.

& {
$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Ref       = if ($env:ENJAMBRE_REF) { $env:ENJAMBRE_REF } else { 'main' }
$Raw       = "https://raw.githubusercontent.com/zsoist/SWARMS/$Ref"
$Zip       = "https://github.com/zsoist/SWARMS/archive/refs/heads/$Ref.zip"
$EnvFile   = Join-Path $HOME '.enjambre.env'
$ClaudeDir = Join-Path $HOME '.claude'
$Utf8      = New-Object System.Text.UTF8Encoding $false   # UTF-8 without BOM: a BOM breaks the first key
$Interactivo = (-not $env:ENJAMBRE_CI) -and [Environment]::UserInteractive

function Paso($t)  { Write-Host ''; Write-Host $t -ForegroundColor Cyan }
function Ok($t)    { Write-Host "[OK] $t" -ForegroundColor Green }
function Falla($t) { throw $t }

function Bajar($url, $destino) {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $destino -ErrorAction Stop
}

function Pedir-Llave($texto) {
    if (-not $Interactivo) { Falla 'No window to ask for the key. Set $env:DEEPSEEK_API_KEY first, then run the installer.' }
    $s = Read-Host -Prompt $texto -AsSecureString
    $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { return ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}

function Guardar-Llave($k) {
    if ($k -notmatch '^sk-') { Falla 'That is not a DeepSeek key (it must start with sk-). Run the installer again.' }
    if (Test-Path $EnvFile) {
        # Keep the other settings. Replace only the key line.
        $lineas = @(Get-Content -Path $EnvFile -Encoding UTF8 | Where-Object { $_ -notmatch '^(export )?DEEPSEEK_API_KEY=' })
        $lineas += "DEEPSEEK_API_KEY=$k"
        if (-not ($lineas | Where-Object { $_ -match '^(export )?ENJAMBRE=' })) { $lineas += 'ENJAMBRE=deepseek' }
    } else {
        $lineas = @(
            '# enjambre settings. Never put this file in git.',
            "DEEPSEEK_API_KEY=$k",
            'ENJAMBRE=deepseek',
            '# Stop a run when it costs more than this (USD).',
            'DEEPSEEK_BUDGET_USD=5',
            '# Workers that run at the same time.',
            'ENJAMBRE_PARALELO=12'
        )
    }
    [IO.File]::WriteAllLines($EnvFile, [string[]]$lineas, $Utf8)
    Ok "Key saved in $EnvFile"
}

function Instalar {
    # 1. uv
    Paso '1/6  uv'
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = (Join-Path $HOME '.local\bin') + ';' + $env:Path
    }
    uv --version
    if ($LASTEXITCODE -ne 0) { Falla 'uv did not install. Close this window, open a new PowerShell, and run the installer again.' }

    # 2. Git for Windows
    Paso '2/6  Git for Windows'
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Ok (git --version)
    } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git -e --source winget --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Falla 'Git did not install. Install it from https://git-scm.com/download/win, then run the installer again.' }
        Ok 'Git installed'
    } else {
        Falla 'Git is missing. Install it from https://git-scm.com/download/win, then run the installer again.'
    }

    # 3. enjambre command
    Paso '3/6  enjambre command'
    uv tool install --force --reinstall --quiet "enjambre @ $Zip"
    if ($LASTEXITCODE -ne 0) { Falla 'The enjambre command did not install. Look at the error above.' }
    uv tool update-shell *> $null
    $bin = (uv tool dir --bin).Trim()
    $env:Path = "$bin;$env:Path"
    $cmd = Get-Command enjambre -ErrorAction SilentlyContinue
    if (-not $cmd) { Falla "The enjambre command is not in $bin. Close this window and run the installer again." }
    Ok $cmd.Source

    # 4. DeepSeek key
    Paso '4/6  DeepSeek key'
    $llaveDeVariable = [bool]$env:DEEPSEEK_API_KEY
    $tiene = (Test-Path $EnvFile) -and (Select-String -Path $EnvFile -Pattern '^(export )?DEEPSEEK_API_KEY=.+' -Quiet)
    if ($llaveDeVariable) {
        Guardar-Llave $env:DEEPSEEK_API_KEY.Trim()
    } elseif ($tiene) {
        Ok "Key found in $EnvFile"
        if ($Interactivo) {
            $k = Pedir-Llave 'Paste a new key to replace it, or push Enter to keep it'
            if ($k) { Guardar-Llave $k }
        }
    } else {
        Guardar-Llave (Pedir-Llave 'Paste your DeepSeek API key (the text does not show) and push Enter')
    }

    # 5. Claude Code skill and global rule
    Paso '5/6  Claude Code skill'
    $skillDir = Join-Path $ClaudeDir 'skills\enjambre'
    New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
    Bajar "$Raw/kit/skills/enjambre/SKILL.md" (Join-Path $skillDir 'SKILL.md')
    Ok "Skill: $skillDir\SKILL.md"
    $tmp = [IO.Path]::GetTempFileName()
    Bajar "$Raw/kit/CLAUDE.global.md" $tmp
    $bloque = [IO.File]::ReadAllText($tmp, $Utf8).TrimEnd() + "`n"
    Remove-Item $tmp
    $reglas = Join-Path $ClaudeDir 'CLAUDE.md'
    $actual = if (Test-Path $reglas) { [IO.File]::ReadAllText($reglas, $Utf8) } else { '' }
    # Remove the old block (if there is one), then add the new block.
    $actual = [regex]::Replace($actual, '(?s)<!-- enjambre:start -->.*?<!-- enjambre:end -->\r?\n?', '')
    if ($actual -and -not $actual.EndsWith("`n")) { $actual += "`n" }
    [IO.File]::WriteAllText($reglas, $actual + $bloque, $Utf8)
    Ok "Rule: $reglas"

    # 6. Opus as the default model (only if no model is set)
    Paso '6/6  Claude Code model'
    $py = @'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
try:
    s = json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}
except json.JSONDecodeError:
    print(f"{p} is not valid JSON. No change. Select Opus in the model menu of Claude.")
    sys.exit(0)
if "model" in s:
    print(f"Model already set in {p}: {s['model']}. No change.")
else:
    s["model"] = "opus"
    p.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    print(f"Set in {p}: model = opus")
'@
    $pyFile = Join-Path ([IO.Path]::GetTempPath()) 'enjambre_modelo.py'
    [IO.File]::WriteAllText($pyFile, $py, $Utf8)
    uv run --quiet --no-project python $pyFile (Join-Path $ClaudeDir 'settings.json')
    Remove-Item $pyFile

    # Test
    Paso 'Test: one small call to DeepSeek'
    $env:PYTHONIOENCODING = 'utf-8'
    enjambre --check
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'The test call failed. Usual causes: a wrong key, or no balance at https://platform.deepseek.com' -ForegroundColor Yellow
        if ($Interactivo -and -not $llaveDeVariable) {
            $k = Pedir-Llave 'Paste the key again (or push Enter to stop)'
            if (-not $k) { Falla 'Stopped. Run the installer again when you have the key.' }
            Guardar-Llave $k
            enjambre --check
            if ($LASTEXITCODE -ne 0) { Falla 'It failed again. Check the key and the balance, then run the installer again.' }
        } else {
            Falla 'The test call failed.'
        }
    }

    Write-Host ''
    Ok 'Ready.'
    Write-Host '   1. Quit Claude completely: right-click the Claude icon near the clock (system tray), then Quit.'
    Write-Host '      Open Claude again. Claude reads the new skill only when it starts.'
    Write-Host '   2. Open a project folder. Ask for a feature. For heavy work, Claude uses the swarm.'
    Write-Host '   3. To force it, write: "use the enjambre skill".'
    Write-Host '   Guide: https://github.com/zsoist/SWARMS/blob/main/START.md'
}

try {
    Instalar
} catch {
    Write-Host ''
    Write-Host "[X] $($_.Exception.Message)" -ForegroundColor Red
    if ($env:ENJAMBRE_CI) { exit 1 }
}
}
