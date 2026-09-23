"""Pruebas sin red de lo que se rompió con GLM el 2026-09-23.

Cada prueba es un hueco real: si vuelve, el CI lo dice antes de que una corrida
"de GLM" termine siendo de DeepSeek en silencio.
  uv run --with pytest pytest -q
"""
import asyncio
import json
import os
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def nucleo(tmp_path, monkeypatch):
    monkeypatch.setenv("ENJAMBRE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-prueba")
    for v in ("SUPABASE_URL", "ENJAMBRE", "WORKER_MODEL", "BRAIN_MODEL", "ENJAMBRE_OPENROUTER_KEY", "ENSAMBLAR", "ENJAMBRE_PARALELO", "MAX_DEEPSEEK_AGENTS"):
        monkeypatch.delenv(v, raising=False)
    sys.modules.pop("enjambre.nucleo", None)
    import enjambre.nucleo as n
    n.VACIOS.clear()
    n.LLAMADAS.clear()
    return n


def respuesta(texto, proveedor="CoreWeave", fin="stop", razon=0):
    return NS(choices=[NS(message=NS(content=texto), finish_reason=fin)], provider=proveedor,
              usage=NS(cost=0.0, prompt_tokens=10, completion_tokens=razon + len(texto),
                       completion_tokens_details=NS(reasoning_tokens=razon)))


def test_flota_por_defecto_es_glm(nucleo):
    assert nucleo.WORKER_MODEL == "z-ai/glm-5.3-flash"
    assert nucleo.BRAIN_MODEL == "z-ai/glm-5.3"


def test_tropa_y_cerebro_tienen_rutas_distintas(nucleo):
    tropa, cerebro = nucleo.afinado_de("z-ai/glm-5.3-flash"), nucleo.afinado_de("z-ai/glm-5.3")
    assert tropa["order"][0] == "CoreWeave"          # la más rápida para flash
    assert "CoreWeave" not in cerebro["order"]       # no sirve el modelo grande
    assert tropa["max_tokens"] >= 24000              # con 8192 el razonamiento se comía la respuesta
    assert nucleo.afinado_de("deepseek-flash") == {}


def test_vacio_se_reintenta_con_el_mismo_modelo_y_otro_proveedor(nucleo, monkeypatch):
    llamadas = []

    async def crear(**kw):
        llamadas.append(kw)
        if len(llamadas) == 1:
            return respuesta("", proveedor="Wafer", fin="length", razon=24000)
        return respuesta('{"bugs": []}')

    monkeypatch.setattr(nucleo.openrouter.chat.completions, "create", crear)
    out = asyncio.run(nucleo.llm("revisa esto", thinking="none"))
    assert out == '{"bugs": []}'
    assert len(llamadas) == 2
    assert all(c["model"] == "z-ai/glm-5.3-flash" for c in llamadas)       # nunca DeepSeek
    assert llamadas[1]["max_tokens"] > llamadas[0]["max_tokens"]
    assert "Wafer" in llamadas[1]["extra_body"]["provider"]["ignore"]
    assert nucleo.VACIOS and nucleo.VACIOS[0]["provider"] == "Wafer"


def test_reintento_del_worker_no_se_va_a_deepseek(nucleo, monkeypatch):
    modelos = []

    async def llm(prompt, model=None, system=None, thinking="none", formato=None):
        modelos.append(model or nucleo.WORKER_MODEL)
        return "" if len(modelos) == 1 else "x" * 200      # el primero falla el gate

    monkeypatch.setattr(nucleo, "llm", llm)
    s = nucleo.Swarm("prueba de reintento con cuatro palabras o más")
    s.cached_plan = [{"id": "t1", "prompt": "haz algo", "deps": [], "filename": "t1.json"}]
    s.ensamblar = False
    asyncio.run(s.run())
    assert modelos and all("deepseek" not in m for m in modelos), modelos


def test_sin_ensamblar_no_llama_al_cerebro(nucleo, monkeypatch, tmp_path):
    async def llm(*a, **k):
        return json.dumps({"bugs": []}) + " " * 100

    async def cerebro(*a, **k):
        raise AssertionError("no debía ensamblar")

    monkeypatch.setattr(nucleo, "llm", llm)
    monkeypatch.setattr(nucleo, "brain", cerebro)
    s = nucleo.Swarm("cacería de bugs de interfaz en tres zonas")
    s.cached_plan = [{"id": "a", "prompt": "p", "deps": [], "filename": "a.json"},
                     {"id": "b", "prompt": "p", "deps": ["a"], "filename": "b.json"}]
    s.ensamblar = False
    asyncio.run(s.run())
    final = (s.run_dir / "FINAL.md").read_text()
    assert "Sin ensamblar" in final and "a.json" in final and "b.json" in final


def _correr(args, env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ENJAMBRE", "OPENROUTER"))}
    env.update(env_extra)
    return subprocess.run([sys.executable, "-c", "import sys;from enjambre.nucleo import cli;sys.argv=['enjambre']+sys.argv[1:];cli()", *args],
                          cwd=RAIZ, env=env, capture_output=True, text=True, timeout=60)


def test_ayuda_explica_en_vez_de_rechazar(tmp_path):
    r = _correr(["--help"], {"ENJAMBRE_DIR": str(tmp_path), "OPENROUTER_API_KEY": "sk-or-v1-prueba"})
    assert r.returncode == 0, r.stderr
    assert "--plan" in r.stdout and "ensamblar" in r.stdout and "flota" in r.stdout


def test_llave_propia_del_enjambre_gana(tmp_path):
    code = "import enjambre.nucleo as n; print(n.OR_KEY)"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ENJAMBRE", "OPENROUTER"))}
    env.update({"ENJAMBRE_DIR": str(tmp_path), "OPENROUTER_API_KEY": "sk-or-v1-sitio", "ENJAMBRE_OPENROUTER_KEY": "sk-or-v1-enjambre"})
    r = subprocess.run([sys.executable, "-c", code], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "sk-or-v1-enjambre", r.stderr


def test_cobertura_gana_la_segunda_si_la_primera_se_rezaga(nucleo, monkeypatch):
    monkeypatch.setattr(nucleo, "HEDGE_S", 0.2)
    llamadas = []

    async def crear(**kw):
        llamadas.append(kw["extra_body"]["provider"]["order"][0])
        if len(llamadas) == 1:
            await asyncio.sleep(5)                 # el rezagado
            return respuesta("tarde")
        return respuesta('{"bugs": ["a tiempo"]}', proveedor=kw["extra_body"]["provider"]["order"][0])

    monkeypatch.setattr(nucleo.openrouter.chat.completions, "create", crear)
    import time as _t
    t0 = _t.monotonic()
    out = asyncio.run(nucleo.llm("revisa", thinking="none"))
    assert out == '{"bugs": ["a tiempo"]}'
    assert _t.monotonic() - t0 < 2                                   # no esperó al rezagado
    assert llamadas[0] != llamadas[1]                                # la segunda arrancó por otro proveedor
    assert nucleo.LLAMADAS[-1]["cubierta"] is True


def test_sin_rezago_no_hay_segunda_peticion(nucleo, monkeypatch):
    llamadas = []

    async def crear(**kw):
        llamadas.append(1)
        return respuesta("rápido y bien")

    monkeypatch.setattr(nucleo.openrouter.chat.completions, "create", crear)
    assert asyncio.run(nucleo.llm("revisa", thinking="none")) == "rápido y bien"
    assert len(llamadas) == 1 and nucleo.LLAMADAS[-1]["cubierta"] is False


def test_compuerta_verifica_por_extension(nucleo):
    c = nucleo.compuerta
    assert c("a.json", '{"bugs": []}') is None
    assert c("a.json", '```json\n{"bugs": []}\n```') is None          # la cerca no cuenta como error
    assert "JSONDecodeError" in c("a.json", '{"bugs": [')
    assert c("a.py", "def f():\n    return 1\n") is None
    assert "SyntaxError" in c("a.py", "def f(:\n")
    assert c("a.md", "cualquier prosa") is None                       # la prosa es del juez


def test_json_roto_se_reintenta_con_el_error_y_con_el_contexto(nucleo, monkeypatch):
    pedidos = []

    async def llm(prompt, model=None, system=None, thinking="none", formato=None):
        pedidos.append({"prompt": prompt, "formato": formato})
        if "da el contexto" in prompt and "devuelve el json" not in prompt:
            return "Contexto de la dependencia, en prosa, suficientemente largo para pasar el gate heurístico sin problema alguno."
        if len([p for p in pedidos if "devuelve el json" in p["prompt"]]) == 1:
            return '{"bugs": [' + '"x", ' * 30                          # largo pero roto
        return json.dumps({"bugs": ["ok"]})                             # corto y válido: no debe reintentarse

    monkeypatch.setattr(nucleo, "llm", llm)
    s = nucleo.Swarm("compuerta de json roto con reintento y contexto")
    s.cached_plan = [{"id": "base", "prompt": "da el contexto", "deps": [], "filename": "base.md"},
                     {"id": "t1", "prompt": "devuelve el json", "deps": ["base"], "filename": "t1.json"}]
    s.ensamblar = False
    # la dependencia contesta prosa larga (pasa el gate) sin llamar al juez
    monkeypatch.setattr(nucleo, "jev_review", lambda *a, **k: asyncio.sleep(0, result={"sin_juez": True, "motivo": "prueba"}))
    asyncio.run(s.run())
    j = [p for p in pedidos if "devuelve el json" in p["prompt"]]
    assert len(j) == 2
    assert all(p["formato"] == "json" for p in j)                    # modo JSON pedido
    assert "no pasa la verificación automática" in j[1]["prompt"]
    assert "[insumo de base]" in j[1]["prompt"]                       # el reintento no pierde el contexto
    assert json.loads((s.ship_dir / "t1.json").read_text()) == {"bugs": ["ok"]}


def test_modo_json_llega_a_openrouter(nucleo, monkeypatch):
    vistos = []

    async def crear(**kw):
        vistos.append(kw["extra_body"].get("response_format"))
        return respuesta('{"ok": true}')

    monkeypatch.setattr(nucleo.openrouter.chat.completions, "create", crear)
    asyncio.run(nucleo.llm("x", formato="json"))
    asyncio.run(nucleo.llm("x"))
    assert vistos == [{"type": "json_object"}, None]


def test_json_valido_corto_no_se_reintenta(nucleo, monkeypatch):
    llamadas = []

    async def llm(prompt, model=None, system=None, thinking="none", formato=None):
        llamadas.append(prompt)
        return '{"bugs": []}'                    # "no encontré nada": 12 caracteres, válido

    monkeypatch.setattr(nucleo, "llm", llm)
    s = nucleo.Swarm("respuesta vacía legítima en json corto")
    s.cached_plan = [{"id": "t1", "prompt": "busca bugs", "deps": [], "filename": "t1.json"}]
    s.ensamblar = False
    asyncio.run(s.run())
    assert len(llamadas) == 1


def test_nueve_tareas_corren_todas_a_la_vez(nucleo):
    assert nucleo.MAX_AGENTS >= 9          # con 8, la novena esperaba turno


def test_razonamiento_desbocado_se_acota_en_el_reintento(nucleo, monkeypatch):
    cuerpos = []

    async def crear(**kw):
        cuerpos.append(kw["extra_body"])
        if len(cuerpos) == 1:
            return respuesta("", proveedor="Parasail", fin="length", razon=24000)
        return respuesta('{"bugs": []}')

    monkeypatch.setattr(nucleo.openrouter.chat.completions, "create", crear)
    assert asyncio.run(nucleo.llm("revisa", thinking="none")) == '{"bugs": []}'
    assert cuerpos[0]["reasoning"] == {"effort": "low"}
    assert cuerpos[1]["reasoning"] == {"max_tokens": 8000}      # acotado, no solo más techo
