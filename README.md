# Enjambre

**Tu propio ejército de agentes baratos, en cualquier terminal.**

Un modelo bueno piensa y reparte el trabajo. Veinte modelos baratos lo ejecutan
en paralelo. Un juez de centavos revisa cada resultado. Tú te quedas con el
entregable.

Funciona desde Claude Code, Codex, tu terminal, o donde sea: es un comando.

```bash
git clone <este-repo> && cd enjambre
cp .env.example .env        # pon UNA llave de API
uv run enjambre "escribe la documentación de este proyecto"
```

---

## Por qué existe

Un modelo caro haciendo todo el trabajo es lento y caro. Pero descomponer una
tarea *bien* sí requiere un modelo caro. La salida es obvia cuando la ves:
**que el caro piense y los baratos suden.**

Lo que este repositorio aporta no es la idea — es lo que aprendimos
rompiéndola durante un día entero, con las cifras al lado.

---

## Las seis lecciones que están cableadas aquí

Cada una nos costó una corrida fallida. Están implementadas, no solo escritas.

### 1. El razonamiento silencioso te vacía las respuestas

Los modelos "flash" modernos razonan por defecto, y **ese razonamiento se cobra
como salida y consume tu presupuesto de tokens**. Si no lo apagas, el modelo
piensa hasta quedarse sin espacio y te devuelve una cadena vacía, cobrándote
igual.

Medido, misma tarea, mismo gateway:

| Modelo | razonamiento | tokens de razonamiento | costo |
|---|---|---|---|
| GLM 5.3 Flash | `effort: low` | **0** | $0.000058 |
| DeepSeek V4.1 Flash | `effort: low` | **400** (todo el presupuesto) | $0.000184 |

En un banco de pruebas de 4 tareas × 3 repeticiones, DeepSeek Flash devolvió
**17% de respuestas vacías**; GLM 5.3 Flash, **0%**. Con veinte workers, ese 17%
son tres tareas perdidas por ronda.

> Y ojo: **GLM no deja apagar el razonamiento**. Devuelve
> `400 Reasoning is mandatory for this endpoint`. Lo que funciona es
> `effort: "low"`, que en la práctica no gasta nada.

### 2. El proveedor que te toca cambia lo que puedes pedir

En un gateway como OpenRouter, un mismo nombre de modelo lo sirven decenas de
proveedores con capacidades **distintas** — y los parámetros que el proveedor no
soporta **se descartan en silencio**. Pides salida estructurada, te cae un
proveedor que no la implementa, y recibes texto libre sin un solo error.

Por eso el enjambre siempre manda `require_parameters`, que obliga a enrutar
solo a proveedores que aceptan todo lo que pediste.

### 3. Paraleliza lo que lee, serializa lo que escribe

El debate del sector se resume así: paralelizar tareas **independientes y de
lectura** funciona; paralelizar tareas que **comparten decisiones implícitas**
produce basura que nadie puede reconciliar después. Dos workers eligen estilos
distintos sin saberlo y el ensamblador hereda el choque.

La regla: si dos subtareas tocan el mismo artefacto, van en serie. Si no,
en paralelo. Y las decisiones que deben compartir (formato, convenciones,
contrato de salida) se **escriben en el plan**, no se dejan implícitas.

### 4. El worker devuelve poco, no todo

Un subagente puede leer lo que quiera, pero devuelve **de 1.000 a 2.000 tokens
destilados**. La capacidad de un modelo para recordar información de su contexto
**cae a medida que el contexto crece**: la ventana es un presupuesto de atención,
no un balde.

### 5. El juez barato tiene puntos ciegos, y hay que conocerlos

Un modelo pequeño juzgando salidas es la diferencia entre un enjambre y un
generador de ruido. Pero se equivoca de formas predecibles, y nosotros las
medimos en carne propia:

- **Juzgando hechos sin la fuente delante**: inventa veredictos. Si vas a
  pedirle que verifique un dato, **pásale la evidencia** o deja que se abstenga.
- **Juzgando un lote de parches**: falla feo. Un parche, un veredicto.
  Nuestro juez rechazó 9 de 11 parches correctos porque le preguntábamos si cada
  uno resolvía *todo* el problema, cuando cada uno era una pieza. Al darle el
  lote como contexto y preguntarle si la pieza *contribuye*, la probabilidad
  pasó de 0.09 a 0.87.
- **Escalas de 1 a 5**: nadie sabe qué hacer con un 3. Rúbricas binarias.

Y lo más importante: **las compuertas deterministas van primero**. Que compile,
que el JSON parsee, que el texto coincida. No pagues un juez sobre algo que ya
sabes que está roto.

### 6. Falla rápido y con jitter

Veinte workers arrancando a la vez son veinte reintentos simultáneos cuando algo
falla. Backoff exponencial **con jitter completo**, un presupuesto global de
reintentos (no solo por llamada), y un tope duro. Un gateway puede además
mantenerte la conexión abierta durante minutos sin responder: pon tu propio
timeout por debajo del suyo.

---

## Cómo se configura

Todo vive en `enjambre/modelos.yaml`, que es un **mapa de roles a modelos**:
planificador, ensamblador, tropa y juez. Cambias ahí, no en el código.

Los secretos van en `.env`, nunca en el YAML. Y los techos de gasto también
están en el YAML: el enjambre se detiene solo al llegar a ellos.

```yaml
roles:
  tropa:
    modelo: z-ai/glm-5.3-flash
    proveedor: openrouter
    paralelo: 8
```

O más rápido todavía, sin tocar archivos:

```bash
WORKER_MODEL="z-ai/glm-5.3-flash" uv run enjambre "tu tarea"
```

---

## Qué NO es

No es un framework. No tiene abstracciones que aprender ni una jerarquía de
clases. Es un orquestador de unos cientos de líneas que hace una cosa: repartir
trabajo entre modelos baratos y juntar los pedazos.

Si necesitas grafos de agentes, memoria persistente o herramientas, hay
frameworks buenos para eso. Este es para cuando quieres veinte manos por unos
centavos y saber exactamente qué está pasando.

---

## Costos reales

De una jornada completa de trabajo real — decenas de corridas, cientos de
subtareas, un simulador de población construido encima:

- **tropa (20 workers, muchas rondas)**: menos de $1
- **juez (una llamada por tarea)**: centavos
- **planificador/ensamblador**: unos pocos dólares

El presupuesto de Anthropic viene en **0** a propósito. Súbelo cuando lo
decidas, no por accidente.

---

## El tablero

```bash
python enjambre/servir.py
```

Abre `localhost:8777`: el DAG de tareas con sus dependencias dibujadas, la línea
de tiempo donde se **ve** el paralelismo (barras que se solapan son trabajo
simultáneo), el costo desglosado y el veredicto del juez tarea por tarea. Sin
build, sin dependencias, un solo archivo HTML.

## Cuándo confiar en el juez — medido, no supuesto

Contrastamos los veredictos del juez contra la verdad verificada a mano
(`enjambre/calibrar_juez.py`). El patrón por tipo de tarea fue inequívoco:

| Tipo de tarea | Aciertos del juez |
|---|---|
| Prosa y textos | **8/8** |
| Generación de código | 2/5 |
| Lote de parches | 1/10 |
| **Verificación de datos** | **0/7** |

La causa está documentada en la literatura: un juez que evalúa **hechos** sin
tener la fuente delante inventa veredictos, y evaluar un **lote** en vez de una
pieza dispara el sesgo de posición. Así que el enjambre solo le pregunta al juez
donde acierta; lo demás lo deciden las compuertas deterministas —que compile,
que el JSON parsee, que el match sea único—, que no se equivocan.

> Salvedad honesta: la muestra son casos que revisamos porque **notamos** algo
> raro, así que sobre-representa los fallos. Las tasas absolutas son pesimistas;
> el patrón por tipo de tarea es el hallazgo que importa.

Mide el tuyo:

```bash
python enjambre/calibrar_juez.py --etiquetar   # etiquetas 20 casos
python enjambre/calibrar_juez.py               # informe
```

Reporta **sensibilidad y especificidad por separado**, nunca "acierto": un juez
que aprueba todo tiene 95% de acierto cuando los fallos son raros, y no sirve
para nada.
