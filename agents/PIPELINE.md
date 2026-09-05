# Orquestación del pipeline de marketing

## Principio

- **Flujos lineales** (un paso detrás de otro, sin ciclos): implementados como Python modular en `marketing_agents/` y coordinados desde `MarketingPipeline`.
- **Flujos que requieren ciclos, trazabilidad explícita o reintentos guiados** (Copywriter ↔ QA): implementados con **LangGraph** en `graph_copy_qa.py`.

LangGraph no sustituye al pipeline completo: solo encapsula el subgrafo donde tiene sentido el estado compartido y las transiciones condicionales.

## Flujo global (alto nivel)

```text
Brief (+ brand_context / paleta / logos del PDF)
  │
  ▼
ContentStrategistAgent          ← lineal (LLM o stub; inbound + brand manual)
  │
  ▼
┌─────────────────────────────┐
│ LangGraph: CopyQAState      │
│   copywriter → qa           │  ← copywriter también lleva inbound + brand
│        ▲         │          │
│        └─ revise ┘          │
│   (hasta max_attempts)       │
└─────────────────────────────┘
  │
  ├─ feed / story / universal ► DesignerAgent
  │                              (brand_campaign_piece si hay manual;
  │                               sin foto: fal / Venice / SD + overlay;
  │                               con foto + alter: Venice /image/edit
  │                               o fal img2img → luego overlay Pillow)
  │                              design_source: generated | user_overlay | user_img2img
  │
  ├─ content_format = reel ──► VideoScriptAgent → VideoDesignerAgent
  │                              (video_gen_mode: full | scenes | still)
  │
  └─ user_clip_reel ─────────► ClipReelDesigner     ← Drive → Whisper → Shotstack
  │
  ▼
HITL (Aprobar / Rechazar / Solicitar cambios → POST /runs/{id}/revise)
  │  social_account_id del run → token+account_id de esa cuenta (multi-cuenta)
  ▼
PublisherAgent (si QA aprobó) ← Meta/IG vía Go sidecar; LinkedIn y X nativo en Python
```

Todo el pipeline emite eventos al **hilo de pensamiento** (`thought_stream.py`) bajo el `trace_id` del run. En modo interactivo se detiene en checkpoints (estrategia, copy, arte) y espera `continue` / `adjust` / `cancel` por `POST /api/thoughts/{trace_id}/reply`.

Fuera del pipeline: **CreativeAdvisorAgent** (`POST /api/advisor/chat`) — coach de marca con contexto del brief y del manual.

Doctrina: `knowledge/inbound_marketing.py` → addendum en Strategist, Copywriter y VideoScriptAgent.

Marca: `brand_manual` + `ocr_paddle` + `brand_scan` + `brand_visual` → `BriefInput.brand_context` / `brand_palette` / `brand_logo_*`.

## Módulos lineales

| Módulo | Rol | Entrada principal | Salida |
|--------|-----|-------------------|--------|
| `strategist.py` | Estrategia de contenido (inbound + brand) | `BriefInput` | `StrategyOutput` |
| `copywriter.py` | Redacción (revisiones QA; inbound + brand) | `StrategyOutput`, opcional `qa_feedback` | `CopyOutput` |
| `designer.py` | Imagen: fal/Venice/SD, foto usuario (+ alter IA), logo marca | `BriefInput`, `CopyOutput`, `StrategyOutput` | `DesignOutput` |
| `image_providers.py` | Generate / `compose_from_user_asset` (edit + overlay) | prompt o asset | URL + `design_source` |
| `revision_prompt.py` | Notas de revisión + `build_scene_edit_prompt` (solo escena) | notes / instructions | prompt edit |
| `venice_client.py` | Venice generate + `/image/edit` (sin `quality` en edit) | bytes + prompt | PNG/JPEG |
| `image_specs.py` | Dimensiones y formatos válidos por red (fuente única) | `red_social`, `content_format` | `ImageSpec` / catálogo |
| `visual_prompt_guards.py` | Sufijo y negativos anti-texto para los generadores | prompt | prompt reforzado |
| `text_contrast.py` | Color de texto según luminancia del fondo | imagen + caja | colores de overlay |
| `thought_stream.py` | Eventos en vivo + checkpoints interactivos | `trace_id` | stream Redis/memoria |
| `brand_manual.py` / `brand_scan.py` / `brand_visual.py` | PDF → texto/OCR/paleta/logos → cues | tenant PDF | assets + cues |
| `advisor.py` | Chat asesor (fuera del pipeline) | mensaje + brief | reply |
| `video_script.py` | Guion reel 3-5 escenas (inbound) | brief, copy, strategy | guion escenas |
| `video_designer.py` | Escenas + voz + Shotstack (still o Venice i2v) | brief, copy, strategy, guion | `VideoDesignOutput` |
| `clip_reel_designer.py` | Reel desde clips Drive | brief, `drive_folder_id` | `VideoDesignOutput` |
| `publisher.py` | Publicación (mock o proveedor real) | plataforma, copy, diseño | `PublishOutput` |
| `quality.py` | Reglas de compliance / tono | texto, `tono_marca` | `QualityReview` |
| `knowledge/inbound_marketing.py` | Doctrina inbound + pirámide redes | — | addendum `_SYSTEM` |

## Subgrafo LangGraph (`graph_copy_qa.py`)

### Estado (`CopyQAState`)

- `brief`, `strategy`: contexto fijo del tramo.
- `copy`, `quality`: última versión del borrador y resultado QA.
- `attempt`: número de ronda de copy (sube en cada visita al nodo copywriter).
- `max_attempts`: tope de rondas (se pasa en `invoke`).
- `events`: lista acumulada (reducer `operator.add`) con un dict por paso para **trazabilidad** (nodo, aprobación, motivos, si hubo feedback previo).

### Transiciones

1. Entrada → **copywriter**: primera vez sin feedback; tras QA fallido, con `quality.reasons` como `qa_feedback` al LLM/stub.
2. **qa**: ejecuta `ContentQualityGuard.validate`.
3. Condición:
   - Si `approved` → **END**.
   - Si no aprobado y `attempt < max_attempts` → otra vuelta a **copywriter** (`revise`).
   - Si no aprobado y ya se alcanzó el tope → **END** (se conserva último copy y `quality`; publicación queda bloqueada en `MarketingPipeline` si `approved` es falso).

### Parámetro `MarketingPipeline(max_copy_qa_attempts=3)`

Controla cuántas rondas de copy como máximo se permiten antes de salir del grafo sin aprobación.

## Salida del pipeline

`MarketingPipeline.run` devuelve un dict que incluye:

- `strategy`, `copy`, `design`, `quality`, `publish_result` (como antes).
- **`copy_qa_trace`**: lista ordenada de eventos del grafo (auditoría / debugging / UI futura).

## Formatos de contenido (`content_format`)

| Formato | Rama | Notas |
|---------|------|-------|
| `feed` | DesignerAgent | Dimensión según `red_social` (IG/FB 1080×1350, LinkedIn 1200×627, X 1200×675) |
| `story` | DesignerAgent (layout centrado) | 9:16; no existe en LinkedIn ni X |
| `universal` | DesignerAgent | 1080×1080 idéntico en todas las redes; se comporta como `feed` en layout y publicación |
| `reel` | VideoScript + VideoDesigner | Async-only, cola `video_render` |
| `user_clip_reel` | ClipReelDesigner | Async-only, requiere `drive_folder_id` + ffmpeg |

El catálogo de qué formatos ofrece cada red vive en `image_specs._NETWORK_FORMATS` y se sirve por `GET /api/image/formats`. **TikTok** genera pero no publica (App Review pendiente). **X** publica nativo (feed con imagen). `_publish_run` devuelve `unavailable` solo para plataformas sin provider.

## Rama Reels (`content_format="reel"`)

- Tras copy/QA, `MarketingPipeline` delega a `VideoScriptAgent` + `VideoDesignerAgent` en lugar de `DesignerAgent`.
- `video_gen_mode`: `full` (Venice genera un clip completo), `scenes` (Venice anima cada toma + Shotstack las une) o `still` (stills + Ken Burns, sin video AI). Modelos resueltos por `venice_video_models.py`; degrada a still si Venice falla.
- Render async vía Celery cola `video_render` (no usar `/runs/sync`).
- Con fal.ai, fondos/voz → Shotstack como URLs `fal.media`; `PUBLIC_IMAGE_BASE_URL` (ngrok) para Meta y assets locales.
- `result["design"]` incluye `video_url` (reels) o `image_url` (feed/story).
- Al aprobar, publica a la cuenta fijada en `social_account_id` (multi-cuenta).

## Manual de marca (inyección)

- Upload: `POST /api/briefs/upload-brand-manual` → `save_brand_manual` (texto + `brand_scan`).
- `_brief_input` carga texto + paleta + rutas de logo en `BriefInput`.
- Strategist/copywriter/video_script: bloques de prompt brand.
- Designer: `resolve_brand_cues` → colores, fonts, `logo_path`, arquetipo `brand_campaign_piece`.

## Foto real + alter IA (Design-as-Code)

Guía operativa: [`docs/foto-real-venice-edit.md`](../docs/foto-real-venice-edit.md).

1. Run con `user_asset_url` + `alter_image_with_ai=true` (+ `visual_instructions` de escena).
2. `DesignerAgent` arma overlay desde copy; para el edit usa `build_scene_edit_prompt` (sin headlines).
3. Si hay `revision_notes` que piden personas/escena y la casilla no venía marcada, el diseñador **auto-activa** el edit.
4. `compose_from_user_asset` → Venice `/image/edit` o fal img2img → Pillow.
5. Fallos de edit: **fail-loudly** (no devolver la foto original en silencio).

## Rama clips usuario (`content_format="user_clip_reel"`)

- Async-only; requiere `drive_folder_id`. Orquestación en `ClipReelDesigner` (Drive → Whisper → hook-scored → captions → wan-effects opcional → Shotstack).
- HITL: Aprobar / Rechazar / **Solicitar cambios** (`POST /runs/{id}/revise` regenera con notas y vuelve a `pending_approval`; nunca publica).
- Publicación: `run.social_account_id` elige la cuenta Meta/LinkedIn destino (`GET /api/auth/accounts`); NULL = cuenta activa más reciente del provider.

## Cuándo ampliar LangGraph

Valor añadido probable:

- Bucles adicionales (p. ej. estratega ↔ stakeholder simulado).
- Ramas condicionales por canal (LinkedIn vs TikTok) con estado compartido pesado.
- Recuperación multi-paso con políticas (backoff, escalado a humano).

Mantener en Python lineal:

- Pasos “una sola vez” sin re-entrada.
- Transformaciones puras cortas (mapeo de DTO, enriquecimiento simple).
