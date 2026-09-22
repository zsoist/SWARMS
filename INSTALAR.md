# Instalar

Tres minutos, una llave de API, cero dependencias exóticas.

## 1. Bájalo

```bash
git clone https://github.com/zsoist/SWARMS.git
cd SWARMS
```

## 2. Pon tu llave

```bash
cp .env.example .env
```

Abre `.env` y pon **una** de estas dos. Con cualquiera ya tienes enjambre:

- `OPENROUTER_API_KEY` — una sola llave, cientos de modelos. [openrouter.ai/keys](https://openrouter.ai/keys)
- `DEEPSEEK_API_KEY` — más barato y con mucha más concurrencia. [platform.deepseek.com](https://platform.deepseek.com)

## 3. Corre algo

```bash
uv run enjambre "escribe la documentación de este proyecto"
```

El planificador descompone el trabajo, la tropa lo ejecuta en paralelo, el juez
revisa, y el ensamblador te entrega el resultado en `runs/<fecha>/FINAL.md`.

## 4. Mira qué pasó

```bash
python enjambre/servir.py
```

Abre `localhost:8777` con el tablero: el DAG de tareas con sus dependencias, la
línea de tiempo donde se ve el paralelismo, el costo y el veredicto del juez
tarea por tarea. Si todavía no has corrido nada, dale a **ver ejemplo**.

---

## Desde Claude Code, Codex o tu editor

No hace falta nada especial: es un comando. Dile a tu agente:

> corre el enjambre con esta tarea: \<lo que sea\>

y que ejecute `uv run enjambre "..."`. El agente lee el `FINAL.md` que queda en
`runs/` y sigue desde ahí.

Si usas Claude Code y quieres instalarlo como plugin (con el campo que te pide
la API key al activarlo):

```bash
/plugin marketplace add zsoist/SWARMS
/plugin install enjambre@SWARMS
```

---

## Cambiar de flota

Por defecto todo corre en **GLM 5.3** vía OpenRouter, porque lo medimos y gana
(ver `README.md`). Para volver a DeepSeek, un interruptor:

```bash
ENJAMBRE=deepseek uv run enjambre "tu tarea"
```

O modelo por modelo, sin tocar archivos:

```bash
WORKER_MODEL="z-ai/glm-5.3-flash"  BRAIN_MODEL="z-ai/glm-5.3"  uv run enjambre "..."
```

O de forma permanente, en `enjambre/modelos.yaml`, que es un mapa de **roles a
modelos**: planificador, ensamblador, tropa y juez.

---

## Cuánto cuesta

Una jornada entera de trabajo real —decenas de corridas, cientos de subtareas—
costó menos de cinco dólares. Una corrida típica de 7 tareas:

```
7 tareas · 51 s · $0.0134
```

El techo de gasto está en `modelos.yaml` y el enjambre se detiene solo al
llegar. El presupuesto de Anthropic viene en **0** a propósito: se sube
queriendo, no por accidente.

---

## Si algo falla

**"falta OPENROUTER_API_KEY"** — no copiaste `.env.example` a `.env`, o la
dejaste vacía.

**Respuestas vacías** — casi siempre es el razonamiento del modelo comiéndose el
presupuesto de salida. Está explicado en el README y ya viene mitigado, pero si
usas un modelo nuevo, revisa que acepte apagar o bajar el razonamiento.

**429 o 402** — límite del gateway. Baja `paralelo` en `modelos.yaml`. El plan
gratuito de OpenRouter va a ~20 peticiones por minuto; DeepSeek nativo aguanta
dos órdenes de magnitud más.
