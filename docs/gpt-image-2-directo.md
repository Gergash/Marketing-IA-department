# gpt-image-2 directo (OpenAI) — comparar coste vs Venice

> **Estado: IMPLEMENTADO.** Proveedor `openai_image` listo para A/B de coste contra Venice.
> El default del `.env` local puede seguir en `venice`; activar `openai_image` solo para la prueba.

## Por qué

Hoy las piezas se pueden generar con **`gpt-image-2` a través de Venice.ai** (`IMAGE_PROVIDER=venice`)
o **directo contra OpenAI** (`IMAGE_PROVIDER=openai_image`). Venice es un revendedor: cobra margen
sobre el mismo modelo. El camino directo elimina ese margen; la calidad es la misma modelo.

## Cómo activar (prueba de coste)

```env
IMAGE_PROVIDER=openai_image
OPENAI_IMAGE_API_KEY=sk-proj-...
OPENAI_IMAGE_API_BASE=https://api.openai.com/v1
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_EDIT_MODEL=gpt-image-2
OPENAI_IMAGE_QUALITY=high
OPENAI_IMAGE_BACKGROUND=opaque
```

**No reutilizar `OPENAI_API_KEY`** si esa key apunta a OpenRouter (LLM de texto). Credenciales
de imagen son propias.

En la UI, `GET /api/image/providers` lista `OpenAI Images (gpt-image-2)` cuando hay key.
Al publicar en staging, `api_usage_events.provider` = `openai_image` (panel admin → Uso por proveedor).
Los logs de gateway incluyen `openai_image.usage` con tokens de la respuesta OpenAI.

## Qué hay en el repo

| Pieza | Archivo |
|-------|---------|
| Settings | `gateway/app/core/settings.py` → `openai_image_*` |
| Cliente HTTP | `agents/marketing_agents/openai_image_client.py` |
| Dispatch generate + edit | `agents/marketing_agents/image_providers.py` (`_openai_image`, `_openai_image_edit`) |
| UI providers | `gateway/app/api/routes.py` → `GET /api/image/providers` |
| Tests | `tests/test_openai_image.py` |
| Env template | `.env.example` |

Legacy `IMAGE_PROVIDER=openai` sigue siendo **DALL·E 3** (`_dalle`); no mezclarlo con `openai_image`.

## Dimensiones

Se pide el `size` estándar más cercano (`1024x1024` / `1024x1536` / `1536x1024`) y Pillow
(`fit_image_to_spec` + overlay) lleva al `ImageSpec` exacto de la red — misma doctrina que Venice.

## Criterio de aceptación (prueba A/B)

1. Misma pieza con `venice` vs `openai_image` → visualmente equivalente.
2. `pytest tests/test_openai_image.py tests/test_venice.py -q` OK.
3. Panel admin muestra eventos `provider=openai_image`.
4. Coste OpenAI (dashboard billing / tokens en log) < factura Venice por imagen equivalente.
