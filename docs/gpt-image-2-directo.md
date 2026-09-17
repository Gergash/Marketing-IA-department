# gpt-image-2 directo (OpenAI) — operación pendiente

> **Estado: DOCUMENTADO, NO IMPLEMENTADO.** Este archivo es el plan de la migración.
> No hay código de `openai_image` en el repo todavía. Ejecutar solo cuando se pida explícitamente.

## Por qué

Hoy las piezas se generan con **`gpt-image-2` a través de Venice.ai** (`IMAGE_PROVIDER=venice`,
`VENICE_IMAGE_MODEL=gpt-image-2`, `VENICE_IMAGE_EDIT_MODEL=gpt-image-2-edit`).
Venice es un revendedor: cobra su margen sobre el mismo modelo de OpenAI.

Llamar a la **API de OpenAI directamente** elimina ese margen. El objetivo es exclusivamente de
coste: la calidad de la imagen es la misma porque el modelo es el mismo.

## Qué existe hoy

| Pieza | Archivo | Estado |
|-------|---------|--------|
| Dispatch de proveedores | `agents/marketing_agents/image_providers.py:51-130` | `stable_diffusion \| fal \| venice \| openai \| canva \| mock` |
| Camino `openai` actual | `image_providers.py:485` (`_dalle`) | **Inservible para esto**: usa `dall-e-3`, ignora el `ImageSpec` (no respeta 1080×1350 / 1080×1920) y no pasa por la composición Pillow |
| Camino Venice (referencia a copiar) | `image_providers.py:381` (`_venice`) y `:669` (`_venice_edit`) | Genera + `_fit_and_overlay` con tipografía Pillow |
| Cliente HTTP Venice | `agents/marketing_agents/venice_client.py` | Modelo a imitar para un `openai_image_client.py` |
| Settings | `gateway/app/core/settings.py:26-79` | Ya hay `openai_api_key` / `openai_api_base` / `openai_model`, pero son del **LLM de texto** (hoy apuntan a OpenRouter en prod) |

## Trampa principal

`OPENAI_API_KEY` y `OPENAI_API_BASE` en producción **están apuntando a OpenRouter**
(`LLM_PROVIDER=openai`, `OPENAI_API_BASE=https://openrouter.ai/api/v1`) para el LLM de texto.
Si el generador de imagen reusa esas variables, las llamadas de imagen se irían a OpenRouter
—que vuelve a ser un revendedor— y la migración no ahorraría nada.

**Por eso el proveedor de imagen necesita credenciales propias y separadas.**

## Plan de implementación

### 1. Settings nuevos (`gateway/app/core/settings.py`)

```python
# Imagen directa contra OpenAI (NO reusar openai_api_key: esa va a OpenRouter para texto)
openai_image_api_key: str = ""
openai_image_api_base: str = "https://api.openai.com/v1"
openai_image_model: str = "gpt-image-2"
openai_image_edit_model: str = "gpt-image-2"
openai_image_quality: str = "high"      # low | medium | high
openai_image_background: str = "opaque"  # opaque | transparent
```

`.env`:

```env
IMAGE_PROVIDER=openai_image
OPENAI_IMAGE_API_KEY=sk-proj-...
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_QUALITY=high
```

### 2. Cliente `agents/marketing_agents/openai_image_client.py`

Espejo de `venice_client.py`:

- `generate(prompt, size, quality) -> bytes` → `POST {base}/images/generations`
- `edit(prompt, image_bytes, size, quality) -> bytes` → `POST {base}/images/edits` (multipart)
- Respuesta en `data[0].b64_json` (gpt-image-2 devuelve base64, no URL como dall-e-3).
- **Fail-loudly**: cualquier error HTTP levanta `RuntimeError("image_gen_failed:openai_image: ...")`.
  No devolver la imagen original ni un placeholder en silencio (misma doctrina que fal/Venice).

### 3. Dimensiones

gpt-image-2 acepta un conjunto cerrado de `size`, no píxeles arbitrarios. Mapear el `ImageSpec`
de `image_specs.py` al `size` más cercano y **reencuadrar con Pillow** al tamaño exacto de la red:

| Formato | `ImageSpec` | `size` a pedir | Ajuste |
|---------|-------------|----------------|--------|
| Feed IG/FB | 1080×1350 | `1024x1536` | recorte vertical centrado |
| Story / Reel | 1080×1920 | `1024x1536` | recorte + upscale |
| Universal | 1080×1080 | `1024x1024` | upscale |
| LinkedIn | 1200×627 | `1536x1024` | recorte horizontal |
| X | 1200×675 | `1536x1024` | recorte horizontal |

El reencuadre ya existe: reusar `_fit_and_overlay` tal como hace `_venice`.

### 4. Enganche en el dispatch

En `image_providers.py:generate_image`, añadir **antes** del bloque `openai` heredado:

```python
if provider == "openai_image" and s.openai_image_api_key:
    url = _openai_image(prompt, s, spec=spec, overlay_text=..., **overlay_extras)
    return url, spec.width, spec.height
if provider == "openai_image" and not s.openai_image_api_key:
    logger.error("image.openai_image_missing_key")
    raise RuntimeError("image_gen_failed:openai_image: missing API key")
```

Y en `compose_from_user_asset` (`image_providers.py:563`) un `_openai_image_edit` paralelo a
`_venice_edit` / `_fal_img2img`, para que **alterar foto real** también funcione directo.

- No tocar `_dalle`: se queda como camino legacy de `IMAGE_PROVIDER=openai`.
- Aplicar `visual_prompt_guards` igual que los demás proveedores (la tipografía la pone Pillow,
  nunca el modelo).

### 5. Exponer en la UI

`GET /api/image/providers` debe listar `openai_image` cuando `OPENAI_IMAGE_API_KEY` esté presente
(mismo patrón condicional que usa hoy Venice).

### 6. Telemetría de coste

Registrar cada llamada en `api_usage_events` (ver el panel de administrador) con
`provider="openai_image"`, para poder comparar en el panel el coste real contra Venice y
confirmar el ahorro.

### 7. Tests

`tests/test_openai_image.py`, calcado de `tests/test_venice.py` / `tests/test_fal_edit.py`:
mock del HTTP, verificar el `size` elegido por formato, que la tipografía la pone Pillow y que un
error del proveedor levanta excepción en lugar de devolver placeholder.

## Criterio de aceptación

1. Una pieza generada con `openai_image` es visualmente equivalente a la de `venice`.
2. `pytest tests/ -q` sin regresiones nuevas.
3. El panel de administrador muestra el evento con `provider=openai_image`.
4. El coste por imagen registrado es menor que el de Venice para el mismo formato.
