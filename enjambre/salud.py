'''Chequeo de salud del enjambre.

`estado()` devuelve un dict con el estado de cada pieza (planificador,
ensamblador, tropa, inspector), de cada proveedor usado (openrouter,
deepseek, anthropic) y del presupuesto. Cada pieza es {ok: bool,
detalle: str} para que el visor pinte un semáforo. Nunca lanza
excepción: si algo falla, la falla ES el resultado. Las llaves jamás
se imprimen ni se devuelven; solo se reporta si están presentes.
'''

import glob
import json
import os
import time
from pathlib import Path
import re

# ── De dónde sale la verdad ───────────────────────────────────────────────
# El .env de la raíz y la configuración del propio núcleo. Si el chequeo se
# inventara los modelos, mentiría justo donde más importa.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass


def _leer_config():
    """Lee tropa, cerebro y juez del núcleo sin ejecutarlo entero."""
    cfg = {"tropa": "?", "cerebro": "?", "juez": "?", "paralelo": 8}
    for ruta in (Path(__file__).resolve().parent / "nucleo.py",
                 Path(__file__).resolve().parent.parent / "orchestrator" / "swarm.py"):
        if not ruta.exists():
            continue
        txt = ruta.read_text(errors="ignore")
        flota = os.environ.get("ENJAMBRE", "glm").lower()
        m = re.search(r'"' + re.escape(flota) + r'":\s*\("([^"]+)",\s*"([^"]+)"\)', txt)
        if m:
            cfg["tropa"], cfg["cerebro"] = m.group(1), m.group(2)
        j = re.search(r'JEV_MODEL\s*=\s*"([^"]+)"', txt)
        if j:
            cfg["juez"] = j.group(1)
        break
    cfg["tropa"] = os.environ.get("WORKER_MODEL", cfg["tropa"])
    cfg["cerebro"] = os.environ.get("BRAIN_MODEL", cfg["cerebro"])
    cfg["paralelo"] = int(os.environ.get("MAX_DEEPSEEK_AGENTS", "8"))
    return cfg


def _proveedor_de(modelo):
    """Un slug con '/' sale por OpenRouter; si no, por la API nativa."""
    return "openrouter" if "/" in (modelo or "") else "deepseek"


_CFG = _leer_config()


import httpx

_DIR_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR_RUNS = os.path.join(_DIR_RAIZ, 'runs')

# nombre: (variable de entorno con la llave, URL de probe GET gratis, headers)
_PROVEEDORES = {
    'openrouter': (
        'OPENROUTER_API_KEY',
        'https://openrouter.ai/api/v1/models',
        None,
    ),
    'deepseek': (
        'DEEPSEEK_API_KEY',
        'https://api.deepseek.com/models',
        lambda k: {'Authorization': 'Bearer ' + k},
    ),
    'anthropic': (
        'ANTHROPIC_API_KEY',
        'https://api.anthropic.com/v1/models',
        lambda k: {'x-api-key': k, 'anthropic-version': '2023-06-01',
                   **({'anthropic-workspace-id': os.environ['ANTHROPIC_WORKSPACE_ID']}
                      if os.environ.get('ANTHROPIC_WORKSPACE_ID') else {})},
    ),
}
_NOMBRES_PROVEEDORES = ('openrouter', 'deepseek', 'anthropic')

_CLAVES_COSTO = ('costo', 'cost', 'gasto', 'spend')


def _config():
    '''Modelos y proveedor de cada pieza; configurable por entorno.'''
    try:
        tropa_n = _CFG['paralelo']
    except Exception:
        tropa_n = 8
    try:
        presupuesto = float(os.environ.get('ENJAMBRE_PRESUPUESTO_USD', '5.0'))
    except ValueError:
        presupuesto = 5.0
    return {
        # NO se inventan modelos: se lee la configuración real del núcleo, que
        # es la que de verdad va a usar el enjambre cuando corra.
        'planificador': (_CFG['cerebro'], _proveedor_de(_CFG['cerebro'])),
        'ensamblador': (_CFG['cerebro'], _proveedor_de(_CFG['cerebro'])),
        'tropa': (_CFG['tropa'], _proveedor_de(_CFG['tropa'])),
        'tropa_n': max(1, tropa_n),
        'inspector': (_CFG['juez'], 'openrouter'),
        'presupuesto': presupuesto,
    }


def _probar_proveedor(nombre):
    '''GET real al listado de modelos del proveedor (no cuesta nada).'''
    var, url, armar_headers = _PROVEEDORES[nombre]
    llave = (os.environ.get(var) or '').strip()
    if not llave:
        return {
            'ok': False,
            'detalle': 'llave ' + var + ' ausente en el entorno',
            'llave_presente': False,
            'latencia_ms': None,
        }
    headers = armar_headers(llave) if armar_headers else {}
    t0 = time.perf_counter()
    try:
        r = httpx.get(url, headers=headers, timeout=10.0)
        lat = int(round((time.perf_counter() - t0) * 1000))
        if r.status_code == 200:
            detalle = 'llave presente y responde (HTTP 200) en ' + str(lat) + ' ms'
        else:
            detalle = 'llave presente pero respondió HTTP ' + str(r.status_code) + ' en ' + str(lat) + ' ms'
        return {
            'ok': r.status_code == 200,
            'detalle': detalle,
            'llave_presente': True,
            'latencia_ms': lat,
        }
    except Exception as exc:
        lat = int(round((time.perf_counter() - t0) * 1000))
        return {
            'ok': False,
            'detalle': 'llave presente pero sin respuesta: ' + type(exc).__name__ + ' (' + str(lat) + ' ms)',
            'llave_presente': True,
            'latencia_ms': lat,
        }


def _gastado():
    """Lo gastado de verdad: la suma de los eventos `done` de cada corrida.

    Rastrear cualquier clave que suene a costo por todo el JSON contaba dos
    veces y sumaba números que no eran dinero.
    """
    import json
    raiz = Path(__file__).resolve().parent.parent
    total, corridas = 0.0, 0
    for log in (raiz / "runs").glob("*-swarm/swarm.jsonl"):
        gasto = None
        for linea in log.read_text(errors="ignore").splitlines():
            try:
                e = json.loads(linea)
            except Exception:
                continue
            if e.get("event") == "done":
                gasto = e.get("spent") or e.get("cost") or {}
        if gasto is not None:
            corridas += 1
            total += sum(v for v in gasto.values() if isinstance(v, (int, float)))
    return total, corridas

def _pieza_modelo(pieza, modelo, proveedor, probes, extra=''):
    p = probes.get(proveedor) or {'ok': False, 'detalle': 'proveedor desconocido: ' + proveedor}
    detalle = (
        pieza + ': modelo ' + str(modelo) + ' vía ' + str(proveedor)
        + ' — ' + p['detalle'] + extra
    )
    return {'ok': bool(p.get('ok')), 'detalle': detalle}


def _con_red(pieza, fn):
    try:
        return fn()
    except Exception as exc:
        return {'ok': False, 'detalle': pieza + ': fallo inesperado: ' + repr(exc)}


def estado():
    '''Estado completo del enjambre. Nunca lanza excepción.'''
    try:
        cfg = _config()
    except Exception as exc:
        return {'ok': False, 'detalle': 'configuración ilegible: ' + repr(exc)}

    probes = {}
    for nombre in _NOMBRES_PROVEEDORES:
        try:
            probes[nombre] = _probar_proveedor(nombre)
        except Exception as exc:
            probes[nombre] = {
                'ok': False,
                'detalle': 'fallo al sondear el proveedor: ' + repr(exc),
                'llave_presente': False,
                'latencia_ms': None,
            }

    sal = {}
    sal['planificador'] = _con_red('planificador', lambda: _pieza_modelo(
        'planificador', cfg['planificador'][0], cfg['planificador'][1], probes))
    sal['ensamblador'] = _con_red('ensamblador', lambda: _pieza_modelo(
        'ensamblador', cfg['ensamblador'][0], cfg['ensamblador'][1], probes))
    sal['tropa'] = _con_red('tropa', lambda: _pieza_modelo(
        'tropa', cfg['tropa'][0], cfg['tropa'][1], probes,
        ' · ' + str(cfg['tropa_n']) + ' agente(s) en paralelo'))
    sal['inspector'] = _con_red('inspector', lambda: _pieza_modelo(
        'inspector', cfg['inspector'][0], cfg['inspector'][1], probes))

    def _presupuesto():
        total, corridas = _gastado()
        restante = cfg['presupuesto'] - total
        ok = restante > 0
        detalle = (
            '$' + format(total, '.4f') + ' gastados de $' + format(cfg['presupuesto'], '.2f')
            + ' según ' + str(corridas) + ' corrida(s) en runs/'
            + ('' if ok else ' — presupuesto agotado')
        )
        return {'ok': ok, 'detalle': detalle}

    sal['presupuesto'] = _con_red('presupuesto', _presupuesto)

    sal['proveedores'] = {
        n: {
            'ok': probes[n]['ok'],
            'detalle': probes[n]['detalle'],
            'llave_presente': probes[n].get('llave_presente', False),
            'latencia_ms': probes[n].get('latencia_ms'),
        }
        for n in _NOMBRES_PROVEEDORES
    }

    piezas_ok = all(
        sal[n]['ok'] for n in ('planificador', 'ensamblador', 'tropa', 'inspector', 'presupuesto')
    )
    proveedores_ok = all(sal['proveedores'][n]['ok'] for n in _NOMBRES_PROVEEDORES)
    sal['ok'] = piezas_ok and proveedores_ok
    return sal


def _fila(nombre, pieza):
    marca = 'OK   ' if pieza.get('ok') else 'FALLA'
    return '  {:<13} {} {}'.format(nombre, marca, pieza.get('detalle', ''))


if __name__ == '__main__':
    e = estado()
    print('== SALUD DEL ENJAMBRE ==')
    if 'proveedores' not in e:
        print('FALLA: ' + e.get('detalle', 'estado desconocido'))
    else:
        print('piezas:')
        for n in ('planificador', 'ensamblador', 'tropa', 'inspector'):
            print(_fila(n, e[n]))
        print('proveedores:')
        for n in _NOMBRES_PROVEEDORES:
            print(_fila(n, e['proveedores'][n]))
        print(_fila('presupuesto', e['presupuesto']))
    print('== ' + ('TODO OK' if e.get('ok') else 'HAY PROBLEMAS') + ' ==')
