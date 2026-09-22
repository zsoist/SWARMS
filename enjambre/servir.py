#!/usr/bin/env python3
"""Abre el tablero del enjambre en el navegador.

    python enjambre/servir.py            # última corrida
    python enjambre/servir.py --puerto 9000

Sirve el tablero y las corridas de runs/ en un servidor local, y abre el
navegador ya apuntando a la última corrida. No hay build ni dependencias.
"""
import argparse
import http.server
import json
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TABLERO = Path(__file__).resolve().parent / "tablero"


def corridas():
    """Las corridas disponibles, de la más nueva a la más vieja."""
    return sorted((d for d in (RAIZ / "runs").glob("*-swarm") if (d / "swarm.jsonl").exists()),
                  key=lambda d: d.name, reverse=True)


def resumen(d):
    """Lo que hay que saber de una corrida SIN abrirla: qué se le pidió, cuándo,
    cuánto tardó, cuánto costó y cuántas tareas salieron.

    Un identificador como '20260922-002225-swarm' no le dice nada a nadie. Lo que
    identifica a una corrida es LO QUE SE LE PIDIÓ."""
    info = {"id": d.name, "reto": "", "cuando": "", "tareas": 0,
            "entregas": 0, "segundos": None, "costo": 0.0, "aprobadas": 0}
    # fecha legible desde el nombre: 20260922-002225 → 22 sep, 00:22
    try:
        f = d.name.split("-")[0]
        h = d.name.split("-")[1]
        MES = ["ene", "feb", "mar", "abr", "may", "jun",
               "jul", "ago", "sep", "oct", "nov", "dic"]
        info["cuando"] = (f"{int(f[6:8])} {MES[int(f[4:6]) - 1]} · "
                          f"{h[:2]}:{h[2:4]}")
    except Exception:
        info["cuando"] = d.name
    for linea in (d / "swarm.jsonl").read_text(errors="ignore").splitlines():
        try:
            e = json.loads(linea)
        except Exception:
            continue
        ev = e.get("event")
        if ev == "start" and e.get("task"):
            info["reto"] = e["task"]
        elif ev == "plan":
            info["tareas"] = len(e.get("tasks") or [])
        elif ev == "ship":
            info["entregas"] += 1
        elif ev == "jev" and (e.get("p") or 0) >= 0.65:
            info["aprobadas"] += 1
        elif ev == "done":
            info["segundos"] = e.get("seconds") or e.get("secs")
            info["costo"] = sum((e.get("spent") or e.get("cost") or {}).values())
    if not info["reto"]:
        info["reto"] = "(sin título)"
    return info


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # índice de corridas, para que el tablero pueda ofrecerlas en un menú
        if self.path == "/salud.json":
            # el visor pregunta al arrancar: ¿está todo conectado?
            try:
                import salud as _s
                datos = _s.estado()
            except Exception as e:
                datos = {"error": f"no pude chequear: {e}"}
            cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        if self.path == "/corridas.json":
            datos = [{**resumen(d), "ruta": f"/runs/{d.name}/swarm.jsonl"}
                     for d in corridas()]
            cuerpo = json.dumps(datos, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        return super().do_GET()

    def translate_path(self, path):
        """/runs/... son las corridas; todo lo demás sale del visor.

        El visor puede vivir en dashboard/ (con sus sprites y su feed) o en
        enjambre/tablero/ (el tablero simple que trae el paquete). Se prefiere
        el primero si existe, porque es el completo.
        """
        if path.startswith("/runs/"):
            return str(RAIZ / path.lstrip("/"))
        rel = path.lstrip("/").split("?")[0] or "index.html"
        for base in (RAIZ / "dashboard", TABLERO):
            cand = base / rel
            if cand.exists():
                return str(cand)
        return str(TABLERO / rel)

    def log_message(self, *a):
        pass  # sin ruido en la consola


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8777)
    ap.add_argument("--sin-abrir", action="store_true")
    a = ap.parse_args()

    cs = corridas()
    print(f"Tablero del enjambre  ·  {len(cs)} corrida(s) disponible(s)")
    if cs:
        print(f"  última: {cs[0].name}")
    url = f"http://localhost:{a.puerto}/"
    print(f"  {url}\n  (Ctrl-C para parar)")
    if not a.sin_abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", a.puerto), Handler) as s:
        try:
            s.serve_forever()
        except KeyboardInterrupt:
            print("\nlisto.")


if __name__ == "__main__":
    main()
