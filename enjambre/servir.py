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
import os
import socketserver
import threading
import webbrowser
from pathlib import Path

RAIZ = Path(os.environ.get("ENJAMBRE_DIR", Path.cwd()))
TABLERO = Path(__file__).resolve().parent / "tablero"


def corridas():
    """Las corridas disponibles, de la más nueva a la más vieja."""
    return sorted((d for d in (RAIZ / "runs").glob("*-swarm") if (d / "swarm.jsonl").exists()),
                  key=lambda d: d.name, reverse=True)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # índice de corridas, para que el tablero pueda ofrecerlas en un menú
        if self.path == "/corridas.json":
            datos = [{"nombre": d.name, "ruta": f"/runs/{d.name}/swarm.jsonl"}
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
        # / → el tablero · /runs/... → las corridas del proyecto
        if path.startswith("/runs/"):
            return str(RAIZ / path.lstrip("/"))
        p = path.lstrip("/") or "index.html"
        return str(TABLERO / p)

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
