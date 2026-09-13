# Foto real + edición IA (Design-as-Code)

> Actualizado: 2026-09-13  
> Flujo: foto del local → **Venice** `gpt-image-2-edit` **o fal** `FLUX Kontext` → tipografía Pillow limpia.

## Qué hace

1. El usuario sube una **foto real** del local (`POST /api/briefs/upload-asset`).
2. Marca **Alterar foto real con IA** y escribe indicaciones de escena (p. ej. “agrega dos personas sentadas en las sillas”).
3. El diseñador edita **solo la escena** con el proveedor elegido:
   - **Venice** → `POST /image/edit` (`gpt-image-2-edit`)
   - **fal.ai** → `fal-ai/flux-pro/kontext` (edición por instrucción; misma capacidad de escena)
4. Pillow aplica headline / subline / CTA / logo **después** — la IA **no** pinta tipografía.

`design_source` en el resultado:

| Valor | Significado |
|-------|-------------|
| `user_img2img` | Foto editada con IA + overlay Pillow (éxito del flujo alterar) |
| `user_overlay` | Solo tipografía sobre la foto original (sin edición de escena) |
| `generated` | Imagen generada desde cero (sin foto de usuario) |

## Configuración `.env`

### Venice

```env
IMAGE_PROVIDER=venice
VENICE_API_KEY=...
VENICE_API_BASE=https://api.venice.ai/api/v1
VENICE_IMAGE_MODEL=gpt-image-2
VENICE_IMAGE_RESOLUTION=2K
VENICE_IMAGE_EDIT_MODEL=gpt-image-2-edit
```

### fal.ai (paridad de edición)

```env
IMAGE_PROVIDER=fal
FAL_API_KEY=...
FAL_MODEL=fal-ai/flux-pro/v1.1
FAL_IMG2IMG_MODEL=fal-ai/flux-pro/kontext
FAL_IMG2IMG_GUIDANCE=3.5
# Solo si usas el legacy strength-based:
# FAL_IMG2IMG_MODEL=fal-ai/flux/dev/image-to-image
# FAL_IMG2IMG_STRENGTH=0.72
```

En el dashboard puedes elegir **fal** o **Venice** por run (`image_provider`); ambos soportan alterar foto real.

## Módulos clave

| Archivo | Rol |
|---------|-----|
| `revision_prompt.py` → `build_scene_edit_prompt` | Prompt **solo-escena** (personas/objetos); prohíbe tipografía |
| `venice_client.py` → `edit_image_bytes` | `POST /image/edit`; re-encode JPEG; **no envía `quality`** |
| `image_providers.py` → `_fal_img2img` / `_fal_edit_arguments` | Upload + Kontext (o img2img legacy) |
| `image_providers.py` → `compose_from_user_asset` | Fit → edit → overlay |
| `designer.py` | Auto-activa alter si las notas de revisión piden cambiar la escena |
| `visual_prompt_guards.py` | Sufijos anti-texto en generación desde cero |

## Contrato Venice `/image/edit` (schema vivo)

Parámetros que **sí** se envían (según modelo):

- `model`, `prompt`, `image` (base64 JPEG), `safe_mode`
- `resolution` (`1K` \| `2K` \| `4K`) en `gpt-image-2-edit` / nano-banana
- `aspect_ratio` del enum Venice (`4:5`, `9:16`, `1:1`, …)

**No enviar `quality`:** el schema tiene `additionalProperties: false` y responde:

```text
400 Unrecognized key(s) in object: 'quality'
```

(La variable `VENICE_IMAGE_EDIT_QUALITY` en `.env` queda documentada como reservada / ignorada por el cliente.)

La fuente se re-encodea a JPEG RGB antes del upload (`_encode_edit_source`) para evitar rechazos “Invalid or corrupt image”.

## Contrato fal edición (Kontext)

- Endpoint default: `fal-ai/flux-pro/kontext`
- Args: `prompt` + `image_url` (+ `guidance_scale` opcional)
- **No** enviar `strength` / `image_size` a Kontext (eso es del legacy `flux/dev/image-to-image`)
- El cliente sube la foto con `fal_client.upload_file` y luego `fal_client.run`
- Alternativa instrucción: `fal-ai/qwen-image-2/edit`

## UI (dashboard)

- Al subir foto se activa **Alterar** y se prellena la indicación de personas.
- El segmento **fal.ai** o **Venice** define quién edita la escena.
- El resultado muestra `fuente: user_img2img` (verde) o aviso si quedó en `user_overlay`.

## Flujo de prueba rápida

1. Un solo Uvicorn en `:8000` (evitar procesos zombi — ver abajo).
2. Frontend → **fal** o **Venice** → subir foto del local → Alterar ON → indicaciones de escena.
3. Manual de marca opcional (PDF Tres Amores, etc.).
4. **Ejecutar Sync** (feed). La edición puede tardar **1–3 minutos**.
5. Verificar: personas en sillas + tipografía legible + `design_source=user_img2img`.

## Troubleshooting

| Síntoma | Causa habitual | Qué hacer |
|---------|----------------|-----------|
| `Unrecognized key(s): 'quality'` | Cliente viejo o API zombi | Un solo proceso en `:8000`; código sin `quality` en el payload |
| `_venice_edit() missing ... 'quality'` | Firma/llamada desalineadas tras hot-reload parcial | Reiniciar Uvicorn limpio |
| Sillas vacías + textos raros | Solo overlay, o IA recibió copy tipográfico | Alterar ON + prompt solo-escena |
| `fal_img2img: ...` / schema | Modelo legacy con args de Kontext o al revés | Usar `FAL_IMG2IMG_MODEL=fal-ai/flux-pro/kontext` |
| `default_provider: fal` con `.env` en venice | Settings cacheados / otro proceso | Matar listeners en `:8000`; settings se re-leen por mtime de `.env` |
| Timeout largo sin 400 | Venice/fal está generando | Esperar; timeout cliente ~120–240s |

### Un solo proceso en el puerto 8000 (Windows)

Varios `uvicorn --reload` dejan workers huérfanos que siguen sirviendo código viejo:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select OwningProcess
# Matar esos PID y los spawn_main hijos; luego un solo:
python -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Tests

```bash
python -m pytest tests/test_venice_edit.py tests/test_fal_edit.py tests/test_revision_prompt.py tests/test_user_assets.py -q
```

## Referencias

- Venice Image Editing: https://docs.venice.ai/guides/media/image-editing  
- API Edit: https://docs.venice.ai/api-reference/endpoint/image/edit  
- fal FLUX Kontext: https://fal.ai/models/fal-ai/flux-pro/kontext  
- Pipeline: [`agents/PIPELINE.md`](../agents/PIPELINE.md)  
- Arranque: [`infra/arranque-stack.md`](../infra/arranque-stack.md)
