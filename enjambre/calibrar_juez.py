#!/usr/bin/env python3
"""¿Cuánto hay que confiar en el juez barato?

Un juez que aprueba casi todo tiene 95% de "acierto" cuando los fallos son
raros, y no sirve para nada. Por eso aquí NO se reporta acierto: se reportan
las dos tasas que importan por separado —

    sensibilidad (TPR)   de lo que SÍ era bueno, ¿cuánto aprobó?
    especificidad (TNR)  de lo que SÍ era malo, ¿cuánto rechazó?

Un juez con sensibilidad baja te tira a la basura trabajo bueno (caro y
frustrante). Uno con especificidad baja deja pasar basura (peor).

Uso:
    python enjambre/calibrar_juez.py                 # informe
    python enjambre/calibrar_juez.py --etiquetar     # etiquetar casos nuevos
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ETIQUETAS = Path(__file__).resolve().parent / "juez_etiquetas.json"
UMBRAL = 0.65            # p >= UMBRAL cuenta como "aprobado" por el juez


def cargar_veredictos():
    """Junta los veredictos de Jev de todas las corridas y de la bitácora."""
    v = []
    for f in sorted(RAIZ.glob("runs/*/swarm.jsonl")):
        for linea in f.read_text(errors="ignore").splitlines():
            try:
                e = json.loads(linea)
            except Exception:
                continue
            if e.get("event") == "jev":
                v.append({"fuente": f.parent.name, "id": e.get("id"),
                          "p": e.get("p"), "calidad": e.get("quality"),
                          "accion": e.get("action")})
    bit = RAIZ / "orchestrator" / "jev_gate.jsonl"
    if bit.exists():
        for linea in bit.read_text(errors="ignore").splitlines():
            try:
                e = json.loads(linea)
            except Exception:
                continue
            v.append({"fuente": "gate_parches", "id": e.get("archivo", "?"),
                      "p": None, "aprobar": e.get("aprobar"),
                      "motivo": e.get("motivo", "")})
    return v


def informe():
    et = json.loads(ETIQUETAS.read_text()) if ETIQUETAS.exists() else {"casos": []}
    casos = et["casos"]
    if not casos:
        print("Sin casos etiquetados todavía. Corre con --etiquetar.")
        return

    vp = vn = fp = fn = 0
    for c in casos:
        aprobo = c["juez_aprobo"]
        bueno = c["realmente_bueno"]
        if bueno and aprobo:
            vp += 1
        elif bueno and not aprobo:
            fn += 1
        elif not bueno and not aprobo:
            vn += 1
        else:
            fp += 1

    print(f"\nCALIBRACIÓN DEL JUEZ — {len(casos)} casos etiquetados a mano\n")
    print(f"{'':>26}{'juez aprobó':>14}{'juez rechazó':>14}")
    print("-" * 54)
    print(f"{'era bueno de verdad':>26}{vp:>14}{fn:>14}")
    print(f"{'era malo de verdad':>26}{fp:>14}{vn:>14}")
    print("-" * 54)

    tpr = vp / (vp + fn) if (vp + fn) else None
    tnr = vn / (vn + fp) if (vn + fp) else None
    if tpr is not None:
        print(f"\nSENSIBILIDAD  {100*tpr:5.1f}%   de lo bueno, cuánto aprobó "
              f"({vp}/{vp+fn})")
        if tpr < 0.8:
            print(f"              ⚠ está botando {100*(1-tpr):.0f}% del trabajo bueno")
    if tnr is not None:
        print(f"ESPECIFICIDAD {100*tnr:5.1f}%   de lo malo, cuánto rechazó "
              f"({vn}/{vn+fp})")
        if tnr < 0.8:
            print(f"              ⚠ está dejando pasar {100*(1-tnr):.0f}% de la basura")

    # dónde falla, por tipo de tarea: esto es lo accionable
    por_tipo = {}
    for c in casos:
        t = c.get("tipo", "sin tipo")
        d = por_tipo.setdefault(t, {"ok": 0, "mal": 0})
        acerto = c["juez_aprobo"] == c["realmente_bueno"]
        d["ok" if acerto else "mal"] += 1
    print("\nPOR TIPO DE TAREA (dónde confiar y dónde no):")
    for t, d in sorted(por_tipo.items(), key=lambda x: -x[1]["mal"]):
        n = d["ok"] + d["mal"]
        print(f"  {t:<28} {d['ok']}/{n} aciertos" +
              ("   ← desconfiar aquí" if d["mal"] > d["ok"] else ""))

    print(f"\nVeredictos disponibles sin etiquetar: "
          f"{len(cargar_veredictos()) - len(casos)}")


def etiquetar():
    """Etiquetado interactivo: tú dices si cada salida era buena de verdad."""
    et = json.loads(ETIQUETAS.read_text()) if ETIQUETAS.exists() else {"casos": []}
    vistos = {(c["fuente"], c["id"]) for c in et["casos"]}
    pendientes = [v for v in cargar_veredictos()
                  if (v["fuente"], v["id"]) not in vistos][:20]
    if not pendientes:
        print("No hay veredictos nuevos por etiquetar.")
        return
    print(f"{len(pendientes)} veredictos por etiquetar. "
          f"Responde s/n (o 'x' para salir).\n")
    for v in pendientes:
        aprobo = (v.get("aprobar") if v.get("p") is None
                  else (v["p"] or 0) >= UMBRAL)
        print(f"  {v['fuente']} · {v['id']} · el juez "
              f"{'APROBÓ' if aprobo else 'RECHAZÓ'}"
              + (f" (p={v['p']:.2f})" if v.get("p") is not None else ""))
        r = input("    ¿era bueno de verdad? [s/n/x] ").strip().lower()
        if r == "x":
            break
        if r not in ("s", "n"):
            continue
        et["casos"].append({**v, "juez_aprobo": bool(aprobo),
                            "realmente_bueno": r == "s",
                            "tipo": input("    tipo de tarea: ").strip() or "sin tipo"})
        ETIQUETAS.write_text(json.dumps(et, ensure_ascii=False, indent=1))
    print(f"\nGuardado en {ETIQUETAS}")


if __name__ == "__main__":
    etiquetar() if "--etiquetar" in sys.argv else informe()
