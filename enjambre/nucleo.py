#!/usr/bin/env python3
"""Swarm v2 — pipeline autónomo ship-first (Build Day Bogotá).

Frontier harness: DAG de tareas + worker pool. Nada de rondas lockstep:
cada tarea se despacha apenas sus dependencias resuelven, cada output se
shippea a disco al instante, y solo lo que falla el gate pasa (una vez)
por un fixer. Sin re-verificación global.

Roles:
  PLANNER    deepseek-v4-pro (o Fable si FABLE_ENABLED=1) — descompone en DAG
             y asigna thinking por tarea (none/low/medium/high)
  WORKER     la tropa de la flota (ENJAMBRE=glm: z-ai/glm-5.3-flash; deepseek:
             deepseek-flash) x8 — thinking por tarea, ejecuta y shippea
  GATE       Jev (typesafe/jev-1.13, OpenRouter /decisions) — juez tipado
             calibrado ~$0.00002/llamada; fallback heurístico sin LLM
  FIXER      el mismo modelo worker — un intento de arreglo solo si el gate falla
  ASSEMBLER  deepseek-v4-pro (o Fable) — ensambla el entregable final

Uso:
    uv run --project orchestrator python orchestrator/swarm.py "tu reto"
    uv run --project orchestrator python orchestrator/swarm.py --demo
"""

import asyncio
import datetime as _dt
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

# La carpeta de trabajo es donde corres el comando, no donde quedó instalado
# el paquete: ahí se leen .env y se escriben runs/. ENJAMBRE_DIR la fija.
ROOT = Path(os.environ.get("ENJAMBRE_DIR", Path.cwd()))
load_dotenv(ROOT / ".env")

MAX_AGENTS = int(os.environ.get("MAX_DEEPSEEK_AGENTS", "8"))
FABLE_ENABLED = os.environ.get("FABLE_ENABLED", "0") == "1"
FABLE_MODEL = os.environ.get("FABLE_MODEL", "claude-fable-5-1")

# Con UNA llave tiene que arrancar. Antes se leían las dos con os.environ[...]
# y sin la de DeepSeek el comando moría con KeyError al importar, aunque la
# flota por defecto (GLM) solo usa OpenRouter. La falta de llave se reporta
# cuando de verdad se necesita, en _exigir_llaves().
deepseek = AsyncOpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY") or "falta-DEEPSEEK_API_KEY",
    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)
openrouter = AsyncOpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY") or "falta-OPENROUTER_API_KEY",
    base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
)


# Mapeo a OpenRouter (IDs verificados contra su catálogo el 2026-09-21;
# ojo: "deepseek/deepseek-chat" allá es un alias viejo de la era V3).
OPENROUTER_EQUIV = {
    "deepseek-flash": "deepseek/deepseek-v4.1-flash",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
}


class Budget:
    """Techos de gasto de hoy (fijados por Daniel). Precios aproximados USD/1M tokens
    (referencia: catálogo OpenRouter 2026-09-21, v4.1-flash / v4-pro)."""

    PRICES = {"deepseek-flash": (0.15, 0.60), "deepseek-v4-pro": (0.57, 1.70)}
    CEILING = {
        "deepseek": float(os.environ.get("DEEPSEEK_BUDGET_USD", "10")),
        "openrouter": float(os.environ.get("OPENROUTER_BUDGET_USD", "10")),
    }

    def __init__(self):
        self.spent = {"deepseek": 0.0, "openrouter": 0.0}
        # Anthropic se mide en tokens (el precio de Fable lo controla el evento);
        # techo duro de los $100 solo si se define ANTHROPIC_PRICE_IN/OUT en .env.
        self.anthropic_in = 0
        self.anthropic_out = 0

    def add(self, provider: str, model: str, usage) -> None:
        if usage is None:
            return
        cost = getattr(usage, "cost", None)  # OpenRouter lo da directo
        if cost is None:
            pi, po = self.PRICES.get(model, (0.55, 2.19))
            cost = (usage.prompt_tokens * pi + usage.completion_tokens * po) / 1e6
        self.spent[provider] += float(cost)
        if self.spent[provider] >= self.CEILING[provider]:
            raise RuntimeError(
                f"💸 Techo de {provider} alcanzado "
                f"(${self.spent[provider]:.2f}/${self.CEILING[provider]})"
            )

    def line(self) -> str:
        return " · ".join(f"{p} ${v:.4f}" for p, v in self.spent.items())


budget = Budget()


# Modelo por defecto de toda la tropa: se cambia con la variable de entorno
# WORKER_MODEL (p.ej. WORKER_MODEL=z-ai/glm-5.3-flash) sin tocar código.
# ── QUIÉN HACE QUÉ ────────────────────────────────────────────────────────
# Por defecto todo corre en GLM 5.3 (Z.ai) vía OpenRouter. DeepSeek queda
# quieto pero listo: un solo interruptor lo devuelve a la vida.
#
#   ENJAMBRE=deepseek  uv run ... swarm.py "tu reto"
#
# La razón del cambio está medida, no supuesta (ver enjambre/README.md):
# DeepSeek flash gastaba su presupuesto de salida en razonamiento silencioso y
# devolvía 17% de respuestas vacías; GLM con effort low gasta CERO tokens de
# razonamiento y devolvió 0% de vacías, por un tercio del costo.
ENJAMBRE = os.environ.get("ENJAMBRE", "glm").lower()

_FLOTAS = {
    # tropa (workers en paralelo) · cerebro (planificador y ensamblador)
    "glm": ("z-ai/glm-5.3-flash", "z-ai/glm-5.3"),
    "deepseek": ("deepseek-flash", "deepseek-v4-pro"),
}
_TROPA, _CEREBRO = _FLOTAS.get(ENJAMBRE, _FLOTAS["glm"])

WORKER_MODEL = os.environ.get("WORKER_MODEL", _TROPA)
BRAIN_MODEL = os.environ.get("BRAIN_MODEL", _CEREBRO)
# Proveedores preferidos en OpenRouter, en orden. Los tres soportan el juego
# completo de parámetros (salida estructurada, seed, penalizaciones) y son los
# más baratos que lo hacen; `allow_fallbacks` deja salir de ahí si se caen.
# dólares por millón de tokens; por encima de esto, otro proveedor
MAX_PRECIO = {"prompt": float(os.environ.get("OR_MAX_PROMPT", "1.0")),
              "completion": float(os.environ.get("OR_MAX_COMPLETION", "3.0"))}
PROVEEDORES_OR = os.environ.get(
    "OPENROUTER_PROVIDERS", "DeepInfra,Morph,Crusoe"
).split(",")

# Afinado por modelo. Un mismo slug lo sirven decenas de proveedores con
# latencias que difieren hasta 17 veces en el primer token, y con tareas cortas
# en paralelo lo que manda es el primer token, no el throughput.
#
# Para GLM, Z.ai recomienda temperature 1.0 y top_p 0.95, y advierte que NO se
# toquen los dos a la vez. El max_tokens tiene que ser generoso: el modelo
# razona obligatoriamente, y si el razonamiento se topa con el techo, devuelve
# una cadena vacía y te la cobra igual.
#
# GLM, medido el 2026-09-23 con una revisión de código de 32k caracteres:
# - effort "low" NO acota el razonamiento en tareas largas: gastó 12.070 tokens
#   pensando. Con max_tokens 8192 el razonamiento se comía todo el techo y
#   `content` volvía vacío (cobrado igual). 7 de 8 y luego 9 de 9 workers vacíos.
# - la ruta importa 16x: DeepInfra/Morph tardó 677 s (más que el timeout de 600);
#   CoreWeave 41 s y BaseTen 63 s, ambos razonando de verdad. Together contestó en
#   3 s con {"bugs":[]} y CERO razonamiento: rápido pero perezoso, fuera.
# - reasoning.max_tokens=2048 recorta, pero la respuesta sale peor (JSON roto).
AFINADO = {
    "glm": {
        "max_tokens": int(os.environ.get("GLM_MAX_TOKENS", "24000")),  # razonamiento + respuesta
        "top_p": 0.95,
        "temp_directo": 1.0,     # Z.ai: no ajustar temperature y top_p a la vez
        "temp_razonando": 1.0,
        "sort": "throughput",    # con salidas largas manda tokens/s, no el primer token
        "order": os.environ.get("GLM_PROVIDERS", "CoreWeave,BaseTen").split(","),
        # Together: 3 s y cero razonamiento (respuesta perezosa). Wafer: razonó hasta
        # el techo de 24k sin contestar, 5 de 9 workers en paralelo (2026-09-23).
        "ignore": ["Together", "Wafer"],
    },
}


def afinado_de(model: str) -> dict:
    """Los parámetros propios del modelo, si los tiene medidos."""
    m = (model or "").lower()
    for clave, cfg in AFINADO.items():
        if clave in m:
            return cfg
    return {}


VACIOS: list = []   # respuestas vacías de la corrida: modelo, proveedor, por qué


async def llm(
    prompt: str,
    model: str = WORKER_MODEL,
    system: str | None = None,
    thinking: str = "none",
) -> str:
    """Una llamada worker. DeepSeek nativo primero (salvo slugs de OpenRouter:
    cualquier modelo con '/' va DIRECTO a OpenRouter), OpenRouter fallback.

    `thinking` (por tarea, lo asigna el planner): "none" apaga el razonamiento
    (flash lo trae ON por defecto — si no se apaga, cada worker paga tokens de
    reasoning a precio de output); "low"/"medium"/"high" usan reasoning_effort.
    """
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    # Un modelo cuyo nombre contiene '/' es un slug de OpenRouter (p.ej.
    # "z-ai/glm-5.3-flash"): NO existe en la API nativa de DeepSeek, así que
    # intentarlo primero sólo gastaría un round-trip fallido por llamada.
    es_openrouter = "/" in model
    if thinking == "none":
        extra_ds = {"reasoning_effort": "none"}
        # Para los slugs de OpenRouter no vale {"reasoning": {"enabled": False}}:
        # GLM lo rechaza con 400 "Reasoning is mandatory for this endpoint and
        # cannot be disabled.". Lo que SÍ funciona es effort "low"; si no se pide
        # effort bajo, el razonamiento se come el max_tokens y `content` vuelve VACÍO.
        if es_openrouter:
            extra_or = {"reasoning": {"effort": "low"}}
        else:
            extra_or = {"reasoning": {"enabled": False}}
        temperature = 0.3
    else:
        extra_ds = {"reasoning_effort": thinking}
        extra_or = {"reasoning": {"effort": thinking}}
        temperature = 0.6  # recomendación paper R1 para modo razonamiento
    if es_openrouter:
        # Slug de OpenRouter: directo allí, sin pasar por DeepSeek nativo.
        #
        # RUTEO DE PROVEEDOR (medido, no supuesto): un mismo modelo lo sirven
        # decenas de proveedores con capacidades DISTINTAS, y OpenRouter descarta
        # en silencio los parámetros que el proveedor enrutado no soporta. En
        # GLM, el endpoint nativo de Z.AI es de los peores para este uso: no
        # soporta salida estructurada ni `seed`. `require_parameters` obliga a
        # enrutar solo a proveedores que aceptan TODO lo que mandamos, así que
        # nunca caemos ahí por accidente.
        af = afinado_de(model)
        prov = {"order": af.get("order", PROVEEDORES_OR), "require_parameters": True,
                "allow_fallbacks": True,
                # Los prompts llevan trabajo del usuario. "deny" saca de la
                # rotación a los proveedores que se reservan el derecho a
                # entrenar con lo que les mandas.
                "data_collection": "deny",
                # Techo por petición, en dólares por millón de tokens. El mismo
                # modelo y los mismos 25 tokens nos costaron 5.25e-06 con un
                # proveedor y 7.25e-06 con otro: sin techo, una ruta cara pasa
                # desapercibida hasta que aparece en la factura.
                "max_price": MAX_PRECIO}
        if af.get("sort"):
            prov["sort"] = af["sort"]
        if af.get("ignore"):
            prov["ignore"] = af["ignore"]
        cuerpo = {"usage": {"include": True}, "provider": prov, **extra_or}
        if af.get("top_p"):
            cuerpo["top_p"] = af["top_p"]
        techo = af.get("max_tokens", 4096)
        for intento in range(2):
            r = await openrouter.chat.completions.create(
                model=model, messages=messages, timeout=900,
                # sin techo explícito, una respuesta larga puede cortarse justo
                # donde el razonamiento se comió el presupuesto
                max_tokens=techo,
                temperature=(af.get("temp_directo" if thinking == "none"
                                    else "temp_razonando", temperature)),
                extra_body=cuerpo,
            )
            budget.add("openrouter", model, r.usage)
            if (r.choices[0].message.content or "").strip():
                break
            # Vacío: casi siempre el razonamiento se comió el techo. Se dice (antes
            # se tragaba en silencio) y se reintenta con el MISMO modelo y más techo.
            u = r.usage
            det = getattr(u, "completion_tokens_details", None)
            VACIOS.append({"model": model, "provider": getattr(r, "provider", None),
                           "finish": r.choices[0].finish_reason,
                           "razonamiento": getattr(det, "reasoning_tokens", None) if det else None,
                           "tokens": getattr(u, "completion_tokens", None)})
            print(f"  ⚠️  {model} devolvió vacío (fin={r.choices[0].finish_reason}, "
                  f"razonó {VACIOS[-1]['razonamiento']} tokens vía {VACIOS[-1]['provider']}); reintento con más techo")
            techo = int(techo * 1.5)
            # y que el reintento no caiga en el mismo proveedor que se quedó pensando
            if VACIOS[-1]["provider"]:
                prov["ignore"] = sorted(set(prov.get("ignore", [])) | {VACIOS[-1]["provider"]})
    else:
        try:
            r = await deepseek.chat.completions.create(
                model=model, messages=messages, timeout=600,
                temperature=temperature, extra_body=extra_ds,
            )
            budget.add("deepseek", model, r.usage)
        except RuntimeError:
            raise  # techo de presupuesto: no hacer fallback, parar
        except Exception:
            r = await openrouter.chat.completions.create(
                model=OPENROUTER_EQUIV.get(model, f"deepseek/{model}"),
                messages=messages, timeout=600, temperature=temperature,
                extra_body={"usage": {"include": True}, **extra_or},
            )
            budget.add("openrouter", model, r.usage)
    return r.choices[0].message.content or ""


# Jerarquía Anthropic para exprimir los $100 del evento:
#   general  → Fable 5.1: SOLO plan inicial y decisiones de máxima palanca
#   officer  → Opus 5: ensamblaje y decisiones intermedias (más barato)
# Con FABLE_ENABLED=0, ambos rangos caen a deepseek-v4-pro (hoy).
RANK_MODELS = {
    "general": os.environ.get("FABLE_GENERAL_MODEL", FABLE_MODEL),
    "officer": os.environ.get("FABLE_OFFICER_MODEL", "claude-opus-5"),
}


async def brain(prompt: str, rank: str = "general") -> str:
    """Planner/assembler: jerarquía Fable/Opus si autorizado, si no deepseek-v4-pro."""
    if FABLE_ENABLED:
        from anthropic import AsyncAnthropic

        ws = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
        client = AsyncAnthropic(
            default_headers={"anthropic-workspace-id": ws} if ws else None
        )
        r = await client.messages.create(
            model=RANK_MODELS[rank], max_tokens=8000,
            # system cacheado: el prefijo se paga una vez por modelo
            system=[{
                "type": "text",
                "text": "Eres el cerebro de un enjambre de agentes deepseek-flash "
                        "en el Build Day de Bogotá. Máxima densidad: cero relleno. "
                        "Cuando se pida JSON, responde SOLO JSON.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        u = r.usage
        budget.anthropic_in += u.input_tokens
        budget.anthropic_out += u.output_tokens
        # con thinking adaptativo el primer bloque puede ser ThinkingBlock:
        # extraer SOLO los bloques de texto, jamás content[0] a ciegas
        return "".join(b.text for b in r.content
                       if getattr(b, "type", "") == "text") or ""
    # Sin Anthropic autorizado, el cerebro es el modelo de la flota elegida:
    # GLM 5.3 por defecto (razona bien y cuesta una fracción), DeepSeek si se
    # cambia el interruptor. thinking="medium": planificar SÍ merece pensar.
    return await llm(prompt, model=BRAIN_MODEL, thinking="medium")


_CERCA = re.compile(r"\A\s*```[a-zA-Z0-9_+-]*[ \t]*\n(.*?)\n?```\s*\Z", re.S)


def sin_cerca(texto: str, extension: str = "") -> str:
    """Quita la cerca de código con la que el modelo envuelve el entregable.

    Pasa todo el tiempo aunque el prompt lo prohíba, y en un archivo de código
    la cerca lo deja inservible: el navegador o el intérprete revientan en la
    primera línea. En un .md una cerca puede ser legítima (un ejemplo dentro
    del texto), así que ahí solo se quita si envuelve el archivo ENTERO.
    """
    if not texto:
        return texto
    m = _CERCA.match(texto)
    if not m:
        return texto
    if extension.lower() in (".md", ".markdown", ".txt") and texto.count("```") > 2:
        return texto          # hay más cercas dentro: son parte del contenido
    return m.group(1) + "\n"


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"Sin JSON en:\n{text[:400]}")
    return json.loads(m.group())


PLAN_PROMPT = """Descompón este reto en un DAG de subtareas para un enjambre de \
{n} agentes baratos en paralelo. Maximiza el paralelismo: solo declara una dependencia \
si el output de otra tarea es INSUMO REAL. Cada prompt debe ser autocontenido y \
pedir un entregable concreto (código, texto, análisis), no un plan.
Asigna "thinking" por tarea — optimiza el costo: "none" para tareas mecánicas \
(redactar, transformar, extraer, formatear), "low"/"medium" para diseño o análisis, \
"high" SOLO para razonamiento pesado (matemáticas, pruebas, algoritmos, debugging \
sutil). Escribe restricciones MEDIBLES y sin ambigüedad ("máximo 250 caracteres", \
no "de 250 caracteres"): un inspector automático las verificará literalmente. \
Añade un campo "titulo" por tarea: frase corta en español, en infinitivo, de máximo 45 caracteres, sin jerga técnica y sin repetir el id — es lo que verá una persona en el visor para entender qué hace la tarea. Responde SOLO JSON:
{{"tasks": [{{"id": "t1", "prompt": "...", "deps": [], "titulo": "redactar la introducción", "thinking": "none", \
"filename": "opcional.ext"}}]}}
Máximo {max_tasks} tareas.

RETO: {task}"""

# Constitución compartida: system prompt IDÉNTICO para todos los workers.
# DeepSeek cachea el prefijo automáticamente — el hit cuesta ~2% del miss,
# así que con 8 workers el contexto común se paga una sola vez.
WORKER_CONSTITUTION = (
    "Eres un agente worker de un enjambre orquestado. "
    "Reglas: (1) entrega el RESULTADO terminado, nunca un plan ni preámbulos; "
    "(2) si la tarea pide código, entrégalo completo y ejecutable; "
    "(3) sé denso: cero relleno, cero disculpas, cero repetir el enunciado; "
    "(4) si un insumo [insumo de tX] contradice la tarea, la tarea manda; "
    "(5) responde en el idioma de la tarea."
)

GATE_BAD = ("i cannot", "i can't", "no puedo", "lo siento, no", "as an ai")


def gate(output: str) -> bool:
    """Gate heurístico de respaldo. Sin LLM: shippear rápido > verificar de más."""
    o = output.strip()
    return len(o) > 80 and not any(b in o[:200].lower() for b in GATE_BAD)


JEV_MODEL = "typesafe/jev-1.13"


JEV_MAX_CALLS = int(os.environ.get("JEV_MAX_CALLS", "60"))
JEV_CALLS = {"n": 0}          # llamadas a Jev consumidas en esta corrida
ESCALATIONS = {"n": 0}        # escaladas a modelo PRO efectivamente aplicadas
PRO_MODEL = os.environ.get("PRO_MODEL", _CEREBRO)


def jev_budget_ok(n=1):
    """Techo de llamadas a Jev por corrida (env JEV_MAX_CALLS, def. 60).
    Agotado devuelve False y jev_review retorna None → el caller cae al gate()
    heurístico local (ship-first: el presupuesto nunca bloquea la misión)."""
    if JEV_CALLS["n"] + n > JEV_MAX_CALLS:
        return False
    JEV_CALLS["n"] += n
    return True


DIAG_INSTR = {
    "completo": "El output está completo, no le falta ninguna parte pedida",
    "restricciones": "El output respeta las restricciones explícitas de la tarea (longitud exacta, formato, cantidad)",
    "sin_relleno": "El output va al grano, sin relleno ni preámbulos",
}
DIAG_KEYS = tuple(DIAG_INSTR)
SESGO_KEY = "sesgo_estereotipo"
DIAG_QUESTIONS = {
    **{k: {"type": "noul", "instructions": v} for k, v in DIAG_INSTR.items()},
    SESGO_KEY: {
        "type": "score",
        "instructions": ("El output trata el territorio, sus instituciones y sus actores "
                         "con datos y matices locales; NO usa estereotipos ni "
                         "generalizaciones sobre la región"),
        "criteria": ["caricatura regional", "estereotipo plano", "aceptable",
                     "matizado", "matizado y anclado en datos locales"],
    },
}

FALLA_NOTA = {
    "completo": "Entrega TODAS las partes pedidas; no omitas ninguna sección ni dato.",
    "restricciones": "Relee las restricciones LITERALES (longitud exacta, formato, cantidad) y cumplelas al pie de la letra.",
    "sin_relleno": "Elimina preámbulos y relleno; ve directo al contenido.",
    SESGO_KEY: ("Sustituye las generalizaciones y los estereotipos sobre la región por datos "
                "concretos, series y fuentes locales, y usa el marco institucional real."),
}


def fallas_a_nota(fallas):
    """Falla → instrucción concreta para el reintento (rechazo ACCIONABLE)."""
    if not fallas:
        return " Relee las restricciones LITERALES de la tarea (longitud exacta, formato, cantidad) y cumplelas."
    return " " + " ".join(FALLA_NOTA[k] for k in fallas)


# Dónde SÍ sirve el juez, medido contra veredictos contrastados a mano
# (enjambre/enjambre/calibrar_juez.py). El patrón fue inequívoco:
#
#   prosa y dossiers        8/8 aciertos   → confiar
#   generación de código    2/5
#   lote de parches         1/10
#   verificación de datos   0/7            → nunca
#
# La causa es conocida y está documentada: un juez que evalúa HECHOS sin tener
# la fuente delante inventa veredictos, y evaluar un LOTE en vez de una pieza
# dispara el sesgo de posición. Así que el juez solo opina donde acierta; lo
# demás lo deciden las compuertas deterministas (que compile, que parsee, que
# el match sea único), que no se equivocan.
# La lista de palabras prohibidas se retiró: era frágil (una tarea de prosa que
# menciona 'verifica' perdía el juez; una de datos que no la mencionaba lo
# gastaba). La decisión ahora es por SEÑALES y devuelve el motivo, medido en
# calibrar_juez.py: prosa 8/8, código 2/5, lote de parches 1/10, datos 0/7.

# Entregable verificable por máquina → lo deciden las compuertas deterministas
# (que compile, que parsee, que el match sea único), no el juez.
_SENAL_VERIFICABLE = (
    "devuelve solo json", "json crudo", "parches", "buscar", "reemplazar",
    "cifras exactas", "auditoría", "auditoria", "hallazgos",
    "código completo", "ejecutable",
)

# Prosa sujeta a criterio → aquí el juez acierta 8 de 8: sí gastar la llamada.
_SENAL_ESTRUCTURAL = ("devuelve solo json", "json crudo", "parches", "reemplazar")
_SENAL_PROSA = (
    "redacta", "resume", "explica", "guion", "guión", "narrativa",
    "dossier", "escribe",
)

_MOTIVO_VERIFICABLE = "entregable verificable por máquina: lo deciden las compuertas"
_MOTIVO_PROSA = "prosa: el juez acierta 8 de 8 aquí"
_MOTIVO_PROSA_PROBABLE = "sin señal clara: prosa es lo más probable y el juez acierta 8 de 8 ahí"

# Extensiones de código o datos → verificable por máquina; de texto → prosa.
_EXT_VERIFICABLE = (".py", ".js", ".json", ".yaml", ".csv")
_EXT_PROSA = (".md", ".txt")


def clasificar_juez(task_prompt: str, filename: str = "") -> tuple[bool, str]:
    """¿Vale la pena gastar una llamada de juez? Devuelve (aplica, motivo).

    Clasificación por señales del entregable, no por palabras prohibidas:
    verificable por máquina → compuertas deterministas; prosa → juez (8/8);
    sin señal clara → decide el filename de la tarea.
    """
    p = task_prompt.lower()
    fn = (filename or "").lower()

    # El TIPO DE ENTREGABLE manda sobre el verbo del encargo: "escribe la
    # función que ordena" es escritura, pero lo que sale es código, y el código
    # lo juzga el intérprete mejor que el juez (medido: 2 aciertos de 5).
    if fn.endswith(_EXT_VERIFICABLE):
        return False, _MOTIVO_VERIFICABLE

    # La extensión manda en los dos sentidos. Un .md es prosa aunque el prompt
    # diga "cifras": pasaba con "no inventes cifras", y cinco documentos se
    # quedaron sin juez justo donde acierta 8 de 8. Solo una señal estructural
    # fuerte (JSON crudo, parches) le gana a la extensión.
    if fn.endswith(_EXT_PROSA):
        if any(s in p for s in _SENAL_ESTRUCTURAL):
            return False, _MOTIVO_VERIFICABLE
        return True, _MOTIVO_PROSA

    for s in _SENAL_VERIFICABLE:
        if s in p:
            return False, _MOTIVO_VERIFICABLE

    for s in _SENAL_PROSA:
        if s in p:
            return True, _MOTIVO_PROSA

    return True, _MOTIVO_PROSA_PROBABLE


def juez_aplica(task_prompt: str, filename: str = "") -> bool:
    """Compatibilidad: firma nueva, solo el booleano."""
    return clasificar_juez(task_prompt, filename)[0]


async def jev_review(task_prompt: str, output: str, filename: str = ""):
    """Jev como inspector Y enrutador: UNA llamada, tres decisiones tipadas.

    - cumple (noul): ¿el output cumple la tarea? → gate
    - calidad (score 0-4): telemetría de deriva de calidad
    - accion (choice): SI NO cumple, qué hacer — esto es la escalera de
      reintentos decidida por un juez calibrado, no por reglas ciegas.
    Devuelve dict o None si Jev no responde (→ gate heurístico local).
    ~$0.00003 por inspección; output tipado, sin parsing, sin loops de juez.
    Presupuesto: JEV_MAX_CALLS (env, def. 60) por corrida; agotado → None (gate() local).
    """
    aplica, motivo = clasificar_juez(task_prompt, filename)
    if not aplica:
        # no es un fallo: es una decisión. El visor muestra el motivo para que
        # el usuario entienda por qué esta tarea no tiene veredicto.
        return {"sin_juez": True, "motivo": motivo}
    if not jev_budget_ok():
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://openrouter.ai/api/alpha/decisions",
                headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                json={
                    "model": JEV_MODEL,
                    "state": f"Tarea encargada:\n{task_prompt[:4000]}\n\n"
                             f"Output entregado:\n{output[:8000]}",
                    "questions": {
                        "cumple": {"type": "noul",
                            "instructions": "El output entregado cumple la tarea encargada"},
                        "calidad": {"type": "score",
                            "instructions": "Calidad del output entregado",
                            "criteria": ["inservible", "pobre", "aceptable", "bueno", "excelente"]},
                        "accion": {"type": "choice",
                            "instructions": "La mejor acción sobre este output",
                            "criteria": {
                                "aprobar": "el output cumple, entregarlo tal cual",
                                "fix_con_feedback": "errores menores, corregir con notas del inspector",
                                "reintentar_pensando_mas": "fallo de razonamiento, reintentar con más pensamiento",
                                "escalar_a_modelo_pro": "demasiado difícil para el modelo rápido, escalar",
                            }},
                        # diagnósticos: hacen el rechazo ACCIONABLE en el fix
                        # (incluye sesgo_estereotipo, score 0-4: <2 dispara nota)
                        **DIAG_QUESTIONS,
                    },
                },
            )
            d = r.json()
            budget.spent["openrouter"] += float(d.get("usage", {}).get("cost") or 0)
            a = d["answers"]
            # sesgo_estereotipo es score 0-4 (0=caricatura regional, 4=matizado):
            # <2 es falla y viaja al fix_prompt como nota explícita.
            diag = {k: float(a[k]["noul"]) for k in DIAG_KEYS}
            diag[SESGO_KEY] = float(a[SESGO_KEY]["score"])
            fallas = [k for k, v in diag.items()
                      if v < (2.0 if k == SESGO_KEY else 0.5)]
            return {"p": float(a["cumple"]["noul"]),
                    "quality": float(a["calidad"]["score"]),
                    "action": a["accion"]["choice"],
                    "diag": diag,
                    "fallas": fallas,
                    "nota": fallas_a_nota(fallas)}
    except Exception:
        return None


THINK_UP = {"none": "low", "low": "medium", "medium": "high", "high": "high"}


class Swarm:
    def __init__(self, task: str, resume_dir: Path | None = None):
        if len(task.split()) < 4 and not resume_dir:
            sys.exit(f"⛔ Reto demasiado vago ({task!r}) — no quemo tokens en eso.")
        self.task = task
        self.run_dir = resume_dir or ROOT / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-swarm"
        self.ship_dir = self.run_dir / "artifacts"
        self.ship_dir.mkdir(parents=True, exist_ok=True)
        self.results: dict[str, str] = {}
        self.sem = asyncio.Semaphore(MAX_AGENTS)
        self.done_events: dict[str, asyncio.Event] = {}
        self.t0 = time.monotonic()
        self._beams: set = set()  # POSTs de telemetría en vuelo
        self._pending_events: list = []  # buffer de telemetría → 1 POST batch
        self._flush_every = float(os.environ.get("SUPABASE_FLUSH_SECONDS", "2"))
        self._flush_n = int(os.environ.get("SUPABASE_FLUSH_EVENTS", "20"))
        self._last_flush = time.monotonic()
        # Checkpoint/resume: replan solo si no hay plan previo en el jsonl.
        self.cached_plan: list | None = None
        jl = self.run_dir / "swarm.jsonl"
        if resume_dir and jl.exists():
            for line in jl.read_text().splitlines():
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue  # línea truncada por un kill: se ignora, no se muere
                if ev.get("event") == "plan":
                    self.cached_plan = ev["tasks"]
                    self.task = ev.get("task", task)
        if resume_dir and self.cached_plan is None:
            sys.exit(f"⛔ {jl} no tiene plan checkpointeado — nada que resumir.")

    def log(self, obj):
        obj = {"t": round(time.time(), 3), **obj}
        with (self.run_dir / "swarm.jsonl").open("a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._beam(obj)

    def _beam(self, obj):
        """Telemetría al Army Dashboard (Supabase). Fire-and-forget: un fallo
        del dashboard JAMÁS toca al enjambre. Buffer en memoria: UN POST batch
        cada ~2s o al juntar N=20 eventos (Supabase REST acepta array)."""
        url = os.environ.get("SUPABASE_URL", "").strip()
        if not url:
            return
        try:
            # La hora del EVENTO, no la de la inserción. Sin esto Supabase
            # pone now() al llegar el lote y los ~20 eventos de un mismo flush
            # aterrizan en el mismo instante: la línea de tiempo se aplana.
            t = obj.get("t")
            ts = (_dt.datetime.fromtimestamp(t, tz=_dt.timezone.utc).isoformat()
                  if isinstance(t, (int, float)) else None)
            self._pending_events.append({
                "run_id": self.run_dir.name,
                "ts": ts,
                "event": obj.get("event", "?"),
                "task_id": obj.get("id"),
                "payload": obj,
            })
            if (len(self._pending_events) >= self._flush_n
                    or time.monotonic() - self._last_flush >= self._flush_every):
                self._flush()
        except Exception:
            pass

    def _flush(self):
        """Drena el buffer en UN POST batch (array JSON, 1 round-trip)."""
        if not self._pending_events:
            return
        batch, self._pending_events = self._pending_events, []
        self._last_flush = time.monotonic()
        url = os.environ.get("SUPABASE_URL", "").strip()
        if not url:
            return
        self._spawn(self._post_batch(url, batch))

    def _spawn(self, coro):
        try:
            task = asyncio.get_running_loop().create_task(coro)
            self._beams.add(task)
            task.add_done_callback(self._beams.discard)
        except Exception:
            coro.close()

    async def _post_batch(self, url, batch):
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    f"{url}/rest/v1/army_events",
                    headers={
                        "apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"],
                        "Content-Type": "application/json",
                    },
                    json=batch,
                )
                if r.status_code >= 500 and len(self._pending_events) < 200:
                    self._pending_events[:0] = batch  # 5xx transitorio: reencolar acotado (4xx = veneno, se suelta)
        except Exception:
            if len(self._pending_events) < 200:
                self._pending_events[:0] = batch

    def ship(self, tid: str, filename: str | None, content: str):
        """Shippear YA: el artefacto toca disco en cuanto existe (escritura atómica)."""
        path = self.ship_dir / Path(filename or f"{tid}.md").name  # sin rutas del planner
        content = sin_cerca(content, path.suffix)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        os.replace(tmp, path)
        print(f"  📦 [{time.monotonic()-self.t0:5.1f}s] {tid} shippeado → {path.name}")

    async def run_task(self, t: dict):
        # Un fallo en UNA tarea jamás tumba la misión (hallazgo del bug-hunt).
        try:
            await self._run_task(t)
        except RuntimeError as e:
            self.log({"event": "error", "id": t["id"], "msg": repr(e)[:400]})
            print(f"  🛑 {e} — abortando misión")
            for ev in self.done_events.values():
                ev.set()
            self.results.setdefault(t["id"], f"(abortado: {e})")
            return
        except Exception as e:
            self.log({"event": "error", "id": t["id"], "msg": repr(e)[:400]})
            print(f"  💥 {t['id']} falló: {repr(e)[:120]}")
            self.results.setdefault(t["id"], f"(falló: {e})")
            self.done_events[t["id"]].set()

    async def _run_task(self, t: dict):
        # Rama ya shippeada en una corrida anterior: reusar, no re-correr.
        prior = self.ship_dir / (t.get("filename") or f"{t['id']}.md")
        if prior.exists():
            self.results[t["id"]] = prior.read_text()
            print(f"  ♻️  {t['id']} recuperado del checkpoint ({prior.name})")
            self.done_events[t["id"]].set()
            return
        for dep in t.get("deps", []):
            try:
                await asyncio.wait_for(self.done_events[dep].wait(), timeout=600)
            except asyncio.TimeoutError:
                raise RuntimeError(f"dep {dep} nunca terminó (¿ciclo en el plan?)")
        context = "\n\n".join(
            f"[insumo de {d}]\n{self.results[d][:2000]}" for d in t.get("deps", [])
        )
        prompt = (context + "\n\n" if context else "") + t["prompt"]
        think = str(t.get("thinking", "none")).strip().lower()
        if think not in THINK_UP:
            think = "none"
        model = WORKER_MODEL   # antes "deepseek-flash" fijo: con ENJAMBRE=glm los reintentos se iban a DeepSeek
        warn = False
        async with self.sem:
            out = await llm(prompt, system=WORKER_CONSTITUTION, thinking=think)
            # Escalera de reintentos ENRUTADA POR JEV (máx 2 fixes, luego se
            # shippea con warn — ship-first, nunca bloquear la misión).
            for attempt in range(2):
                # Gate heurístico ANTES de Jev: vacío, rechazo o <80 chars ya
                # está condenado — no le pagamos una inspección Jev (~12k chars)
                # a lo que solo puede acabar en fix.
                if attempt == 0 and not gate(out):
                    self.log({"event": "jev_skip", "id": t["id"], "chars": len(out)})
                    out = await llm(f"Este output falló ({out[:300]!r}). Entrega el "
                                    f"resultado completo para: {t['prompt']}",
                                    model=model, system=WORKER_CONSTITUTION,
                                    thinking=think)
                    continue
                jv = await jev_review(t["prompt"], out, t.get("filename", ""))
                if jv and jv.get("sin_juez"):
                    self.log({"event": "jev", "id": t["id"], "p": None,
                              "sin_juez": True, "motivo": jv["motivo"]})
                    break
                if jv is None:  # Jev caído → gate heurístico local, sin reintentos ciegos
                    if not gate(out) and attempt == 0:
                        out = await llm(f"Este output falló ({out[:300]!r}). Entrega el "
                                        f"resultado completo para: {t['prompt']}",
                                        system=WORKER_CONSTITUTION, thinking=think)
                    break
                self.log({"event": "jev", "id": t["id"], "p": jv["p"],
                          "quality": jv["quality"], "action": jv["action"],
                          "diag": jv["diag"]})
                # Pasa si cumple, si Jev dice aprobar, o si la calidad es
                # "bueno"+ (>=3/4): un juez literalista no bloquea trabajo usable.
                if jv["p"] >= 0.5 or jv["action"] == "aprobar" or jv["quality"] >= 3.0:
                    break
                # Jev decide el siguiente paso; el feedback viaja en el prompt
                if jv["action"] == "reintentar_pensando_mas":
                    think = THINK_UP[think]
                elif jv["action"] == "escalar_a_modelo_pro":
                    # Escalada EFECTIVA: cambia model/thinking del SIGUIENTE intento
                    # (persisten al próximo ciclo del for) y queda en telemetría.
                    model, think = PRO_MODEL, "medium"
                    ESCALATIONS["n"] += 1
                    self.log({"event": "jev_escalado", "id": t["id"],
                              "model": model, "from": WORKER_MODEL,
                              "quality": jv["quality"], "fallas": jv["fallas"]})
                print(f"  🔧 {t['id']} rechazado por Jev (p={jv['p']:.2f}, "
                      f"calidad={jv['quality']:.1f}) → {jv['action']}")
                fallas = (" Falló en: " + ", ".join(jv["fallas"]) + "."
                          if jv["fallas"] else
                          " Relee las restricciones LITERALES de la tarea "
                          "(longitud exacta, formato, cantidad) y cúmplelas.")
                out = await llm(
                    f"Un inspector calificó tu output {jv['quality']:.1f}/4 y lo "
                    f"rechazó.{fallas}\nOutput rechazado:\n{out[:1500]}\n\n"
                    f"Entrega la versión corregida y completa de: {t['prompt']}",
                    model=model, system=WORKER_CONSTITUTION, thinking=think)
            else:
                warn = True
                self.log({"event": "warn", "id": t["id"],
                          "msg": "shippeado sin aprobación de Jev tras 2 fixes"})
        self.results[t["id"]] = out
        self.ship(t["id"], t.get("filename"), out)
        self.log({"event": "shipped", "id": t["id"], "chars": len(out), "warn": warn})
        self.done_events[t["id"]].set()

    async def run(self):
        self.log({"event": "start", "task": self.task[:500]})
        if self.cached_plan is not None:
            tasks = self.cached_plan
            print(f"♻️  Plan recuperado del checkpoint ({len(tasks)} tareas)")
        else:
            print(f"🧠 Planner ({'Fable' if FABLE_ENABLED else 'deepseek-v4-pro'})…")
            plan = extract_json(await brain(PLAN_PROMPT.format(
                n=MAX_AGENTS, max_tasks=MAX_AGENTS * 2, task=self.task
            )))
            tasks = plan["tasks"]
        ids = {t["id"] for t in tasks}
        for t in tasks:  # sanear deps que no existen para no colgar el DAG
            t["deps"] = [d for d in t.get("deps", []) if d in ids]
        # Dos tareas con el mismo archivo se pisan en silencio: la segunda
        # sobrescribe a la primera y el informe lista el nombre dos veces. Se
        # resuelve al cargar el plan, prefijando el id a la repetida.
        vistos = set()
        for t in tasks:
            nombre = Path(t.get("filename") or f"{t['id']}.md").name
            if nombre.lower() in vistos:
                nuevo = f"{t['id']}-{nombre}"
                print(f"⚠️  {t['id']}: «{nombre}» ya lo escribe otra tarea → {nuevo}")
                t["filename"] = nuevo
                nombre = nuevo
            vistos.add(nombre.lower())
        self.done_events = {t["id"]: asyncio.Event() for t in tasks}
        if self.cached_plan is None or getattr(self, "plan_needs_log", False):
            self.log({"event": "plan", "task": self.task, "tasks": tasks})
        print(f"🚀 DAG con {len(tasks)} tareas — despacho continuo, sin barreras")

        await asyncio.gather(*(self.run_task(t) for t in tasks))

        if (self.run_dir / "FINAL.md").exists() and all(
            (self.ship_dir / (t.get("filename") or f"{t['id']}.md")).exists()
            for t in tasks
        ):
            print("♻️  FINAL.md ya existe y todas las ramas están shippeadas — nada que hacer.")
            self._flush()  # el resume idempotente también drena su telemetría
            if self._beams:
                await asyncio.gather(*self._beams, return_exceptions=True)
            return
        print("🧠 Assembler…")
        try:
            final = await brain(rank="officer", prompt=
                f"Ensambla el entregable final para: {self.task}\n\nPiezas:\n"
                + "\n\n".join(f"## {k}\n{v[:3000]}" for k, v in self.results.items())
            )
            tmp = self.run_dir / "FINAL.md.tmp"
            tmp.write_text(final)
            os.replace(tmp, self.run_dir / "FINAL.md")  # atómico: exists() es la señal de resume
        except Exception as e:
            # ship-first hasta el final: las piezas YA están en artifacts/; un
            # assembler caído no puede silenciar el 'done' ni perder telemetría.
            print(f"⚠️ assembler caído ({type(e).__name__}: {e}) — las piezas "
                  f"quedan en {self.ship_dir}, FINAL.md pendiente")
        self.log({"event": "done", "seconds": round(time.monotonic() - self.t0, 1),
                  "spent": budget.spent, "tasks": len(self.results)})
        # Parte final: "listo, aquí está lo que pediste"
        jevs = {}
        for l in (self.run_dir / "swarm.jsonl").open():
            try:
                e = json.loads(l)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "jev":
                jevs[e["id"]] = e
        print(f"\n✅ LISTO — aquí está lo que pediste "
              f"({time.monotonic()-self.t0:.0f}s · {budget.line()}):")
        print(f"   flota: {WORKER_MODEL}"
              + (f" · ⚠️ {len(VACIOS)} respuestas vacías reintentadas "
                 f"({', '.join(sorted({str(v['provider']) for v in VACIOS}))})" if VACIOS else " · 0 respuestas vacías"))
        self.log({"event": "flota", "worker": WORKER_MODEL, "vacios": VACIOS})
        for tid in self.results:
            j = jevs.get(tid)
            fn = tasks and next((t.get("filename") for t in tasks if t["id"] == tid), None)
            print(f"   • {self.ship_dir / (fn or tid + '.md')}"
                  + (f"  [sin juez: {j.get('motivo','')[:34]}]" if j and j.get("sin_juez")
                     else f"  [Jev {j['p']*100:.0f}%]" if j and j.get("p") is not None
                     else ""))
        print(f"   • {self.run_dir}/FINAL.md  (entregable ensamblado)")
        # drenar telemetría antes de que muera el loop (o el 'done' nunca llega)
        self._flush()
        if self._beams:
            await asyncio.gather(*self._beams, return_exceptions=True)


def _exigir_llaves():
    """Falla temprano y en castellano, no con un 401 a mitad de corrida."""
    usa_or = "/" in WORKER_MODEL or "/" in BRAIN_MODEL
    usa_ds = not ("/" in WORKER_MODEL and "/" in BRAIN_MODEL)
    faltan = []
    if usa_or and not os.environ.get("OPENROUTER_API_KEY"):
        faltan.append("OPENROUTER_API_KEY")
    if usa_ds and not os.environ.get("DEEPSEEK_API_KEY"):
        faltan.append("DEEPSEEK_API_KEY")
    if faltan:
        sys.exit(f"⛔ falta {', '.join(faltan)} en {ROOT / '.env'} "
                 f"(flota «{ENJAMBRE}»: {WORKER_MODEL} + {BRAIN_MODEL})")


def cli():
    """Punto de entrada del comando `enjambre`."""
    if len(sys.argv) < 2:
        sys.exit('Uso: enjambre "reto" | --demo | --resume runs/<dir> | --plan plan.json')
    _exigir_llaves()
    if sys.argv[1] == "--plan":
        # Plan autorado por Fable (Claude Code): los workers ejecutan tal cual.
        # No loggear aquí: fuera del event loop el beam a Supabase se pierde;
        # run() lo loggea porque plan_needs_log queda en True.
        spec = json.loads(Path(sys.argv[2]).read_text())
        s = Swarm(spec.get("task", "plan externo"))
        s.cached_plan = spec["tasks"]
        s.plan_needs_log = True
        asyncio.run(s.run())
        sys.exit(0)
    if sys.argv[1] == "--resume":
        rd = Path(sys.argv[2])
        rd = rd if rd.is_absolute() else ROOT / rd
        asyncio.run(Swarm("(resume)", resume_dir=rd).run())
        sys.exit(0)
    task = (
        "Escribe un README corto para un proyecto que orquesta agentes "
        "baratos en paralelo: qué hace, cómo se instala y un ejemplo."
        if sys.argv[1] == "--demo"
        else " ".join(sys.argv[1:])
    )
    asyncio.run(Swarm(task).run())


if __name__ == "__main__":
    cli()
