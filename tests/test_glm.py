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
    for v in ("SUPABASE_URL", "ENJAMBRE", "WORKER_MODEL", "BRAIN_MODEL", "ENJAMBRE_OPENROUTER_KEY", "ENSAMBLAR"):
        monkeypatch.delenv(v, raising=False)
    sys.modules.pop("enjambre.nucleo", None)
    import enjambre.nucleo as n
    n.VACIOS.clear()
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

    async def llm(prompt, model=None, system=None, thinking="none"):
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
