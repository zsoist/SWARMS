# CLAUDE.md — SWARMS (enjambre)

Un cerebro planifica, una tropa barata ejecuta en paralelo, un juez revisa.
Todo el núcleo está en `enjambre/nucleo.py`. Uso y números: `README.md`.

## Comandos

```bash
uv run --with pytest pytest -q                       # antes de cada push (sin red)
uv run enjambre --help
node ejemplos/banco_proveedores.mjs <modelo> <prompt.txt> <prov...>   # re-medir rutas
```

## Reglas, cada una por algo que ya pasó

- **La flota por defecto es GLM y tiene que contestar GLM.** Nada de modelos
  fijos en el código: los reintentos usan `WORKER_MODEL`. Un `"deepseek-flash"`
  fijo mandó 16 de 17 respuestas "de GLM" a DeepSeek sin que nadie lo notara.
- **Techo de tokens generoso para GLM** (razona aunque pidas effort low):
  24k la tropa, 32k el cerebro. Con 8.192 volvía `content` vacío, cobrado.
- **Tropa y cerebro tienen rutas distintas** (`AFINADO`, gana la clave más
  larga). El modelo grande no lo sirven los mismos proveedores ni al mismo precio.
- **Una respuesta vacía nunca se traga en silencio:** se registra en `VACIOS`,
  sale en la línea `flota:` y se reintenta con el mismo modelo en otro proveedor.
- **Rutas por medición, no por marca:** los proveedores cambian cada semana.
  Antes de tocar `order`/`ignore`, mide con `ejemplos/banco_proveedores.mjs`.
- **Llave propia** (`ENJAMBRE_OPENROUTER_KEY`): compartir llave con una app
  pública le cerró el tope diario a esa app.
- **Secretos solo en `.env`**; el repo es público.
- **Cada arreglo, con su prueba en `tests/`**: que falle con el bug y pase sin él.
