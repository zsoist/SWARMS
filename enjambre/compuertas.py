#!/usr/bin/env python3
"""Ciclo autónomo de fixes: hallazgos → agentes escriben PARCHES → se aplican
con compuertas (match exacto + chequeo de sintaxis). Claude aprueba el lote.

Uso:
  python scripts/autofix.py plan <run_dir_hallazgos>   # emite orchestrator/plans/fixes.json
  python scripts/autofix.py apply <run_dir_parches>    # aplica con compuertas
  python scripts/autofix.py gate <run_dir_parches>     # auditoría seca (dry-run)
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVO_POR_TAREA = {
    # De qué archivo habla cada tarea. Los parches se validan por match único
    # contra el archivo destino, así que un mapeo errado se rechaza solo — pero
    # mejor acertar. Llénalo con las tareas de TU proyecto:
    #
    #   "mi_tarea": "ruta/al/archivo.py",
}
SALTAR = set()  # ids de tarea que NO se parchean automáticamente
def archivo_de(stem):
    if stem in ARCHIVO_POR_TAREA:
        return ARCHIVO_POR_TAREA[stem]
    return DEFAULT_FILE
DEFAULT_FILE = os.environ.get("ARCHIVO_POR_DEFECTO", "")

# ── Compuerta semántica Jev (3ª compuerta: compilar != ser correcto) ──────────
try:  # carga opcional de ROOT/.env vía dotenv (si está instalado); silenciosa si no
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"
JEV_TIMEOUT = 90          # segundos por llamada
RIESGO_MAX = 2            # escala Jev 0-4: >2 => RECHAZA. Calibra con: autofix.py gate <run_dir>
JEV_APAGADA = os.environ.get("JEV_GATE", "1") == "0"   # JEV_GATE=0 => compuerta off (emergencia)
JEV_LOG = ROOT / "orchestrator" / "jev_gate.jsonl"


def jev_gate_parche(hallazgo: dict, buscar: str, reemplazar: str,
                    idx: int = 0, total: int = 1, lote_txt: str = "") -> dict:
    """Compuerta semántica: ¿este parche RESUELVE el hallazgo SIN romper la lógica?
    (compilar != ser correcto: flags de stop invertidos, guardas desactivadas,
    comparaciones giradas, estado mutado, orden de efectos, excepciones tragadas).
    FAIL-CLOSED: sin API key, error de red o respuesta ilegible => aprobar=False.
    Devuelve {'aprobar','riesgo','resuelve','efecto_colateral','motivo','costo_usd'}."""
    res = {"aprobar": False, "riesgo": 4, "resuelve": "",
           "efecto_colateral": "", "motivo": "", "costo_usd": 0.0}

    if JEV_APAGADA:
        res.update(aprobar=True, riesgo=0, motivo="compuerta desactivada (JEV_GATE=0)")
        return res

    key = (os.environ.get("ENJAMBRE_OPENROUTER_KEY") or os.environ.get("OPENROUTER_API_KEY", "")).strip()
    if not key:
        res["motivo"] = "sin OPENROUTER_API_KEY — fail-closed"
        return res

    # contrato Jev: state = el material a juzgar; noul lleva SOLO instructions;
    # score lleva instructions + criteria como ARRAY (verificado en el harness)
    payload = {
        "model": JEV_MODEL,
        "state": (
            f"HALLAZGO: {json.dumps(hallazgo, ensure_ascii=False)}\n\n"
            f"EL ARREGLO COMPLETO SON {total} PARCHE(S). Este es el número {idx + 1}.\n"
            + (f"LOTE COMPLETO (contexto, no lo juzgues suelto):\n{lote_txt}\n\n" if total > 1 else "")
            + f"PARCHE A JUZGAR — BUSCAR (código actual, literal):\n{buscar}\n\n"
            f"REEMPLAZAR (propuesto, literal):\n{reemplazar}"
        ),
        "questions": {
            "resuelve": {
                "type": "noul",
                "instructions": (
                    "Este parche es una PARTE del arreglo: la afirmación es que CONTRIBUYE "
                    "correctamente a resolver el HALLAZGO y no lo contradice. NO exijas que este "
                    "parche solo resuelva todo el hallazgo: juzga el lote completo como arreglo y "
                    "este parche como su pieza. Juzga semántica, no sintaxis: si invierte flags/stop, "
                    "desactiva guardas, gira condiciones (>= vs >), muta estado de más, cambia orden "
                    "de efectos o traga excepciones, la afirmación es FALSA."
                ),
            },
            "riesgo": {
                "type": "score",
                "instructions": (
                    "Riesgo (0-4) de romper comportamiento existente al aplicar el parche: "
                    "0 = trivial y demostrablemente seguro; 4 = cambia semántica fuera del "
                    "hallazgo."
                ),
                "criteria": [
                    "sube por cada rama o llamador afectado fuera del hallazgo",
                    "sube por cada flag, guarda o condición de borde tocada",
                    "baja si el cambio es local, aditivo y reversible",
                ],
            },
            "sin_colateral": {
                "type": "noul",
                "instructions": (
                    "Aplicar REEMPLAZAR NO cambia el comportamiento de ninguna otra ruta, "
                    "llamador, flag o contrato fuera del hallazgo. Si el HALLAZGO pide "
                    "explícitamente un cambio de alcance amplio (por ejemplo modificar un "
                    "prompt o una regla que usan todas las voces), ese alcance ES el hallazgo "
                    "y NO cuenta como efecto colateral."
                ),
            },
        },
    }

    req = urllib.request.Request(
        JEV_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=JEV_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:                      # red, 4xx/5xx, timeout, JSON roto
        pista = " (¿SSL? córrelo con: uv run --project orchestrator python scripts/autofix.py)" if "SSL" in str(e) or "CERTIFICATE" in str(e).upper() else ""
        res["motivo"] = f"Jev inaccesible ({type(e).__name__}: {e}){pista} — fail-closed"
        return res

    ans = data.get("answers") or (data.get("data") or {}).get("answers") or {}
    try:  # noul = PROBABILIDAD 0-1 de que la afirmación sea cierta
        p_res = float((ans.get("resuelve") or {}).get("noul"))
        p_col = float((ans.get("sin_colateral") or {}).get("noul"))
        riesgo = int(round(float((ans.get("riesgo") or {}).get("score"))))
    except (TypeError, ValueError):
        res["motivo"] = "respuesta Jev ilegible — fail-closed"
        return res
    res["resuelve"] = f"p={p_res:.2f}"
    res["efecto_colateral"] = f"p_sin_colateral={p_col:.2f}"

    aprobar = p_res >= 0.65 and p_col >= 0.55 and riesgo <= RIESGO_MAX
    res.update(aprobar=aprobar, riesgo=riesgo,
               motivo="" if aprobar else f"p_res={p_res:.2f} p_col={p_col:.2f} riesgo={riesgo}",
               costo_usd=float((data.get("usage") or {}).get("cost", 0.0) or 0.0))
    try:                                        # bitácora auditable de cada veredicto
        with JEV_LOG.open("a") as fh:
            fh.write(json.dumps({"archivo": hallazgo.get("archivo", ""), "aprobar": aprobar,
                                 "riesgo": riesgo, "motivo": res["motivo"],
                                 "resuelve": res["resuelve"][:400],
                                 "efecto_colateral": res["efecto_colateral"][:200],
                                 "buscar": buscar[:160], "reemplazar": reemplazar[:160]},
                                ensure_ascii=False) + "\n")
    except Exception:
        pass
    return res


def _hallazgo_de(run_dir: Path, f: Path, archivo: str) -> dict:
    """Recupera el hallazgo original que originó fx_<stem>_<i>.json, para dar contexto real a Jev."""
    stem, _, idx = f.stem.replace("fx_", "", 1).rpartition("_")
    try:
        d = json.loads(clean((run_dir / "artifacts" / f"{stem}.json").read_text()))
        altas = [h for h in d.get("hallazgos", []) if h.get("gravedad") == "alta"]
        h = dict(altas[int(idx)])
    except Exception:
        h = {}
    h.setdefault("archivo", archivo)
    h.setdefault("tarea", stem)
    return h


def jev_gate_lote(hallazgo: dict, pares: list) -> list:
    """Juzga TODOS los parches de un archivo en paralelo (3x90 s en serie bloquean; en hilo no).
    pares = [(buscar, reemplazar), ...] -> lista de veredictos en el MISMO orden."""
    if not pares:
        return []
    lote_txt = "\n".join(f"--- parche {i + 1}/{len(pares)} ---\nBUSCAR:\n{b}\nREEMPLAZAR:\n{r}"
                         for i, (b, r) in enumerate(pares))
    with ThreadPoolExecutor(max_workers=min(4, len(pares))) as ex:
        return list(ex.map(lambda ib: jev_gate_parche(hallazgo, ib[1][0], ib[1][1],
                                                      ib[0], len(pares), lote_txt),
                           enumerate(pares)))


def clean(t):
    return re.sub(r"^```(?:json)?|```$", "", t.strip(), flags=re.M).strip()


def plan(run_dir: Path):
    tasks = []
    for f in sorted(run_dir.glob("artifacts/*.json")):
        try:
            d = json.loads(clean(f.read_text()))
        except Exception:
            continue
        if f.stem in SALTAR:
            continue
        archivo = archivo_de(f.stem)
        code = (ROOT / archivo).read_text()
        altas = [h for h in d.get("hallazgos", []) if h.get("gravedad") == "alta"]
        for i, h in enumerate(altas[:3]):
            tasks.append({
                "id": f"fx_{f.stem}_{i}", "thinking": "medium",
                "filename": f"fx_{f.stem}_{i}.json",
                "prompt": (
                    'Devuelve SOLO JSON crudo: {"parches":[{"buscar":"...","reemplazar":"..."}]} '
                    "— máximo 3 parches quirúrgicos que arreglen SOLO este hallazgo. "
                    "REGLAS DURAS: 'buscar' debe ser una subcadena EXACTA y ÚNICA del código "
                    "(cópiala literal, con sus espacios y saltos); 'reemplazar' la versión "
                    "corregida completa de ese fragmento; NO reformatees nada más; NO toques "
                    "otras funciones; conserva el estilo. Si el hallazgo no es arreglable con "
                    'parches seguros, devuelve {"parches":[]}.\n\n'
                    f"HALLAZGO en {archivo}: [{h.get('donde','?')}] {h.get('problema','')} "
                    f"FIX SUGERIDO: {h.get('fix','')}\n\nCÓDIGO COMPLETO:\n```\n{code[:60000]}\n```"
                ),
            })
    out = ROOT / "orchestrator" / "plans" / "fixes.json"
    json.dump({"task": "Parches quirúrgicos para los hallazgos de gravedad alta.",
               "tasks": tasks}, out.open("w"), ensure_ascii=False)
    print(f"{len(tasks)} tareas de fix → {out}")


def check(path: Path) -> bool:
    if path.suffix == ".js":
        return subprocess.run(["node", "--check", str(path)],
                              capture_output=True).returncode == 0
    if path.suffix == ".py":
        return subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                              capture_output=True).returncode == 0
    if path.suffix == ".html":
        js = re.search(r"<script>(.*)</script>", path.read_text(), re.S)
        p = Path("/tmp/_chk.js"); p.write_text(js.group(1) if js else "")
        return subprocess.run(["node", "--check", str(p)],
                              capture_output=True).returncode == 0
    return True


def apply(run_dir: Path):
    aplicados, rechazados = [], []
    for f in sorted(run_dir.glob("artifacts/fx_*.json")):
        try:
            parches = json.loads(clean(f.read_text())).get("parches", [])
        except Exception:
            rechazados.append((f.stem, "json inválido")); continue
        stem = f.stem.replace("fx_", "").rsplit("_", 1)[0]
        rel = archivo_de(stem)
        archivo = ROOT / rel
        original = archivo.read_text()
        texto, ok, pares = original, True, []
        for p in parches:
            b, r = p.get("buscar", ""), p.get("reemplazar", "")
            if not b or texto.count(b) != 1:      # compuerta 1: match exacto y único
                ok = False; break
            texto = texto.replace(b, r)
            pares.append((b, r))
        if not ok or texto == original:
            rechazados.append((f.stem, "sin match único o vacío")); continue
        archivo.write_text(texto)
        if not check(archivo):                     # compuerta 2: sintaxis
            archivo.write_text(original)
            rechazados.append((f.stem, "rompía sintaxis — revertido")); continue
        # compuerta 3: SEMÁNTICA (Jev) — un parche puede compilar y aun envenenar la lógica
        veredictos = jev_gate_lote(_hallazgo_de(run_dir, f, rel), pares)
        malos = [(i, v) for i, v in enumerate(veredictos) if not v["aprobar"]]
        if malos:
            archivo.write_text(original)
            detalle = "; ".join(f"parche[{i}] riesgo={v['riesgo']} ({v['motivo']})" for i, v in malos)
            rechazados.append((f.stem, f"Jev RECHAZA — revertido: {detalle}"))
            continue
        aplicados.append(f.stem)
    print(f"✅ aplicados: {aplicados}")
    print(f"⛔ rechazados: {rechazados or 'ninguno'}")


def gate(run_dir: Path):
    """Auditoría SECA (dry-run): juzga los parches pendientes sin tocar archivos.
    Sirve para calibrar RIESGO_MAX y ver el costo antes de aplicar."""
    ok = no = 0
    for f in sorted(run_dir.glob("artifacts/fx_*.json")):
        try:
            parches = json.loads(clean(f.read_text())).get("parches", [])
        except Exception:
            print(f"{f.stem}: json inválido"); continue
        stem = f.stem.replace("fx_", "").rsplit("_", 1)[0]
        rel = archivo_de(stem)
        codigo = (ROOT / rel).read_text()
        hallazgo = _hallazgo_de(run_dir, f, rel)
        usables = [(p.get("buscar", ""), p.get("reemplazar", "")) for p in parches
                   if p.get("buscar") and codigo.count(p["buscar"]) == 1]
        if len(usables) != len(parches):
            print(f"{f.stem}: {len(parches) - len(usables)} parche(s) sin match único — omitidos")
        for i, v in enumerate(jev_gate_lote(hallazgo, usables)):
            print(f"{'APRUEBA' if v['aprobar'] else 'RECHAZA'} {f.stem}[{i}] "
                  f"riesgo={v['riesgo']:>3} colateral={v['efecto_colateral'][:60]!r} "
                  f"motivo={v['motivo'] or '-'}")
            ok += 1 if v["aprobar"] else 0
            no += 0 if v["aprobar"] else 1
    print(f"\n{run_dir.name}: {ok} aprobables, {no} rechazables "
          f"(costo ~${0.00003 * (ok + no):.6f})")


if __name__ == "__main__":
    cmd, run = sys.argv[1], Path(sys.argv[2])
    run = run if run.is_absolute() else ROOT / run
    {"plan": plan, "apply": apply, "gate": gate}[cmd](run)
