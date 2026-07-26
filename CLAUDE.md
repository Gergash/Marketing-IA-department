# Marketing DEPA IA — Scope de Proyecto

## Qué es este proyecto

MVP de automatización de marketing con agentes de IA. Flujo: brief → estrategia → copy con QA → diseño visual → aprobación humana → publicación en redes.

**Prioridad de desarrollo:** un solo developer, mediados 2026, iterar rápido sin sobre-ingenierizar.

---

## Arquitectura

```
Frontend React/Vite (:5173)
        ↓
Gateway FastAPI (:8000)  ←→  PostgreSQL + Redis (Docker)
        ↓
Celery worker (async) + APScheduler (campañas)
        ↓
Pipeline Python (agents/marketing_agents/)
        ↓
Go sidecar social-publisher (:8088) → Meta Graph API
```

### Pipeline de agentes

```
Strategist → LangGraph [Copywriter ↔ QA] → Designer → Publisher
```

Doctrina inbound (HubSpot/Cyberclick/Postedin/EUDE/NothingAD/RD Station) vive en
`agents/marketing_agents/knowledge/` y se inyecta en Strategist, Copywriter y VideoScriptAgent.
Pirámide de fines en redes: **Entretener → Informacion → Conexion**; el contenido debe llegar
a la comunidad del brief (`publico_objetivo`), no a audiencia genérica.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| API | FastAPI + Alembic (Python 3.10) |
| Agentes | LangGraph + LangChain |
| LLM | Ollama / Anthropic / OpenAI — configurable vía `.env` |
| Imágenes | **fal.ai (Flux Pro)** — principal; DALL·E y SD como alternativas |
| Video (Reels) | **Shotstack** (block-and-poll, env `stage` sandbox / `v1` prod) — principal; JSON2Video documentado, no implementado |
| Voz (voiceover) | **fal.ai Kokoro Spanish** — principal en dev (reusa `FAL_API_KEY`); ElevenLabs / OpenAI TTS como alternativas |
| Transcripción (clips usuario) | **Whisper** (`whisper-1`, timestamps por palabra) — principal; mock para tests |
| Fuente de clips | Google Drive (OAuth `drive.readonly`) — carpeta privada del usuario |
| Social | Meta/IG OAuth + Go publisher; LinkedIn; mocks |
| Async | Celery + Redis (worker default + worker dedicado `-Q video_render` para reels y user_clip_reel) |
| Scheduler | APScheduler |
| Frontend | React + Vite |
| DB | PostgreSQL (Docker) |

---

## Estructura de archivos clave

```
agents/marketing_agents/
  knowledge/            — doctrina verificada (inbound + redes); se inyecta en prompts
  strategist.py         — tipo de post, hook, mensaje base (inbound: atraer→convertir→cerrar→deleitar)
  copywriter.py         — copy + headline/subline; pirámide Entretener→Informacion→Conexion
  graph_copy_qa.py      — bucle LangGraph Copywriter ↔ QA
  quality.py            — reglas de calidad de diseño
  designer.py           — arquetipo editorial + prompt Flux + composición PIL
  publisher.py          — publicación vía proveedor social
  image_providers.py    — generación, overlay post-proceso e img2img
  user_assets.py        — carga y fit de fotos del usuario
  layout_archetypes.py  — 4 arquetipos editoriales
  design_layouts.py     — composición PIL por arquetipo
  video_script.py       — VideoScriptAgent: guion 3-5 escenas, hook/CTA, banda 15-30s (arco inbound)
  video_timeline.py     — contrato Timeline/Scene/VoiceoverTrack (Pydantic) + to_shotstack_edit()
                          (títulos = clips TitleAsset en pista overlay; media abajo; sin `title_asset`)
  video_providers.py    — render_video(): Shotstack; fal CDN o reescribe localhost→PUBLIC_IMAGE_BASE_URL
  voice_providers.py    — synthesize_voice(): fal TTS / ElevenLabs / OpenAI TTS / mock
  video_designer.py     — VideoDesignerAgent: escenas fal.ai + voz + Timeline + render
  drive_source.py       — OAuth Google Drive: listar y descargar clips de una carpeta
  transcription_providers.py — transcribe_clips(): Whisper (ffmpeg extrae audio) / mock
  clip_assets.py        — clip_public_url(): mapea path local de clip a URL servida
  clip_editor.py         — ClipEditorAgent: selección hook-scored de segmentos (banda 6-60s)
  clip_reel_designer.py — ClipReelDesigner: Drive → transcripción → selección → [efecto] → Timeline → render
  pipeline.py            — MarketingPipeline: orquesta el flujo completo Strategist→...→Publisher
  llm.py                 — cliente LLM configurable (Ollama/Anthropic/OpenAI)
  overlay_text.py        — helpers de overlay tipográfico sobre imagen
  social_providers.py    — abstracción de proveedor social (Go sidecar / mocks)
  schemas.py              — modelos internos de datos del pipeline
  image_specs.py          — specs de dimensión/aspecto por plataforma-formato

gateway/app/
  api/routes.py          — endpoints principales
  api/auth_social.py     — OAuth Meta/LinkedIn
  core/settings.py       — configuración (carga .env)
  core/auth.py           — dependencia require_auth usada por los endpoints
  core/logging.py        — configuración de logging
  db/session.py          — sesión SQLAlchemy
  db/schema_patches.py   — parches de esquema fuera de Alembic
  models/entities.py     — modelos ORM
  services/pipeline_service.py   — orquestación del pipeline
  services/scheduler_service.py  — lógica de campañas/APScheduler
  schemas/contracts.py   — Pydantic schemas entrada/salida

workers/tasks.py        — tareas Celery
```

---

## Convenciones de código

- **Python 3.10** — sin features de 3.11+
- Schemas Pydantic v2 en `gateway/app/schemas/`
- Agentes son funciones puras cuando es posible; estado explícito vía LangGraph solo en Copy/QA
- Un proveedor principal por servicio + alternativas configurables; no hardcodear el proveedor
- No agregar manejo de errores para escenarios imposibles; confiar en las garantías del framework
- Sin comentarios que expliquen QUÉ hace el código; solo comentarios para WHY no obvios
- No crear archivos de documentación salvo petición explícita

---

## Arquetipos de diseño (no cambiar IDs)

| ID | Cuándo usar |
|----|------------|
| `typographic_poster` | Promocional / ventas |
| `minimal_conceptual` | Informativo |
| `editorial_infographic` | Educativo / branding |
| `cinematic_hero` | Storytelling / entretenimiento |

---

## Dimensiones de imagen por plataforma

| Plataforma/Formato | Dimensión | Aspecto |
|--------------------|-----------|---------|
| Instagram/Facebook feed | 1080×1350 | 4:5 |
| Stories/Reels (imagen) | 1080×1920 (~810×1440 fal) | 9:16 |
| Reel (video, `content_format=reel`) | 1080×1920, 30fps | 9:16 |
| Reel con clips propios (`content_format=user_clip_reel`) | 1080×1920, 30fps | 9:16 (duración 6-60s, no 15-30s del reel generado) |
| LinkedIn feed | 1200×627 | — |

fal.ai escala proporcionalmente si altura > 1440px.

---

## Config `.env` típica en dev

```env
IMAGE_PROVIDER=fal
FAL_API_KEY=...
FAL_MODEL=fal-ai/flux-pro/v1.1
FAL_IMG2IMG_MODEL=fal-ai/flux/dev/image-to-image
FAL_IMG2IMG_STRENGTH=0.72
VIDEO_PROVIDER=shotstack
SHOTSTACK_API_KEY=...          # key sandbox → SHOTSTACK_ENV=stage; key prod → v1
SHOTSTACK_ENV=stage
VIDEO_MAX_WAIT_SECONDS=600
VIDEO_FPS=30
VOICE_PROVIDER=fal             # reusa FAL_API_KEY; alt: elevenlabs | openai | mock
VOICE_LANGUAGE=es
FAL_TTS_MODEL=fal-ai/kokoro/spanish
FAL_TTS_VOICE=ef_dora
# ELEVENLABS_API_KEY=...       # solo si VOICE_PROVIDER=elevenlabs
# ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
STT_PROVIDER=whisper
EFFECTS_ENABLED=false
FAL_EFFECTS_MODEL=fal-ai/wan-effects
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/callback/google
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/marketing_mvp
REDIS_URL=redis://localhost:6379/0
SOCIAL_PROVIDER=meta
GO_PUBLISHER_URL=http://localhost:8088
PUBLIC_IMAGE_BASE_URL=https://TU-NGROK   # Meta + assets locales; reel fal usa fal.media
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
```

**Nunca commitear `.env`.**

**Reel es async-only:** `content_format=reel` (y también `user_clip_reel`) requiere `POST /api/runs/async` (se rechaza con 422 en `/runs/sync`) y un **segundo worker Celery** en la cola dedicada:

```bash
python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render
```

Tras cambiar `.env` o código de video, **reinicia el worker** (Celery no recarga env ni módulos solos).

**`user_clip_reel` requiere además `ffmpeg` instalado en el host** (se invoca vía `subprocess` para extraer el audio de cada clip antes de transcribir con Whisper) y `drive_folder_id` en el request.

---

## Cómo levantar el stack (7 terminales)

```bash
# 1 - Infra
docker compose -f infra/docker-compose.yml up -d

# 2 - Ollama (si LLM_PROVIDER=ollama)
ollama serve

# 3 - Gateway
uvicorn gateway.app.main:app --reload --port 8000

# 4 - Worker Celery (cola default: feed/story)
python -m celery -A workers.celery_app.celery_app worker -l info

# 4b - Worker video_render (obligatorio para reel / user_clip_reel)
python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render

# 5 - Frontend
cd frontend && npm run dev

# 6 - Go publisher (solo al publicar)
cd microservices/social-publisher-go && go run .

# 7 - ngrok (Shotstack + Meta; actualizar PUBLIC_IMAGE_BASE_URL y reiniciar Uvicorn + workers)
ngrok http 8000
```

---

## API endpoints relevantes

- `POST /api/briefs/upload-asset` — subir foto del usuario (multipart)
- `POST /api/runs/sync` / `/async` — ejecutar pipeline (`user_asset_url`, `alter_image_with_ai`, `visual_instructions`, `archetype_override`, `content_format` incluye `reel` y `user_clip_reel`; ambos solo vía `/async`, 422 en `/sync`; `user_clip_reel` requiere `drive_folder_id`, 422 si falta)
- `POST /api/runs/{id}/approve` / `/reject` — aprobación humana
- `POST /api/campaigns/{id}/fire` — disparar campaña
- `GET /api/image/archetypes` — listar arquetipos disponibles
- `GET /api/image/providers` — listar proveedores de imagen

---

## Tests

```bash
pytest tests/ -v
```

Archivos clave:
- `tests/test_pipeline.py` — pipeline sync/async con mock
- `tests/test_graph_copy_qa.py` — reintentos Copy/QA
- `tests/test_scheduler.py` — campañas → `pending_approval`
- `tests/test_layout_archetypes.py` — specs 4:5, fal scaling; IoT/cámara sin diluir por `"ia" in tema`
- `tests/test_design_layouts.py` — composición PIL: 4 layouts, fallback
- `tests/test_user_assets.py` — foto usuario + overlay sin fal
- `tests/test_linkedin_native.py` — LinkedIn con imagen (mock)
- `tests/test_inbound_knowledge.py` — doctrina inbound inyectada en estratega/copy/video_script
- `tests/test_video_timeline.py` — contrato Timeline/Scene, `to_shotstack_edit()`, clamp de duración
- `tests/test_voice_providers.py` — `synthesize_voice` (mock/ElevenLabs/OpenAI/fal, default español)
- `tests/test_video_providers.py` — `render_video` (mock/Shotstack poll, publicize URLs, body de error 400)
- `tests/test_video_designer.py` — `VideoDesignerAgent.run` end-to-end mockeado
- `tests/test_video_pipeline.py` — `MarketingPipeline.run(content_format="reel")` end-to-end + regresión feed
- `tests/test_pipeline_service_video.py` — `_media_url` y persistencia de `video_url`
- `tests/test_drive_source.py` — OAuth Google Drive: listar/descargar clips, sanitización de nombre de archivo
- `tests/test_transcription_providers.py` — Whisper mockeado, chunking >25MB con offset-correction
- `tests/test_clip_editor.py` / `tests/test_clip_assets.py` — selección hook-scored banda 6-60s, stub determinístico
- `tests/test_clip_reel_designer.py` — `ClipReelDesigner` end-to-end mockeado, wan-effects (éxito/degradación), reset de trim tras efecto, captions multi-segmento
- `tests/test_contracts_user_clip_reel.py` — validación de `RunRequest` (`drive_folder_id` obligatorio) y límite de columna
- `tests/test_video_timeline_clips.py` — contrato Timeline: overlays TitleAsset + clips video/captions
- `tests/test_format_normalization.py` — normalización de `content_format` en requests
- `tests/test_runs_api.py` — endpoints `/api/runs` (sync/async, validaciones 422)
- `tests/conftest.py` — fixtures compartidas de la suite

---

## Decisiones arquitectónicas fijas

- **ComfyUI: descartado** (GPU local insuficiente para Flux; usar fal.ai)
- **Prometheus:** activable con `PROMETHEUS_ENABLED=true` → `/metrics` (compatible con FastAPI 0.115); off en dev por defecto
- **Go publisher:** no duplicar lógica de publicación Meta en Python si Go ya intentó
- **Anti-duplicados IG:** error 9007 indica container no `FINISHED` — manejar sin reintentar ciegamente
- **ngrok**: obligatorio para Meta (publicar) y para assets **locales** (`user_clip_reel`, overlays Pillow). En Reels con fal.ai, fondos/voz van a Shotstack como URLs `fal.media` (sin depender del túnel en el render)
- **Reel es async-only:** `content_format="reel"` (y `user_clip_reel`) se rechaza con 422 en `/runs/sync`; corre solo vía `/runs/async` en la cola Celery dedicada `video_render` — requiere levantar un **segundo worker** (`python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render`) además del worker default
- **Video sin retries:** la tarea `execute_video_pipeline_task` usa el `celery.Task` base plano (sin `autoretry_for`) para no re-renderizar video ante errores transitorios (costo/duplicados); timeout extendido ~20 min vía `task_annotations` en `celery_app.py`
- **Contrato Shotstack:** `to_shotstack_edit()` emite pistas `captions → títulos → media` (tracks[0] = capa superior). Los overlays son clips `asset.type=title` (estilo Shotstack `minimal`/`subtitle`), **nunca** una propiedad `title_asset` dentro del clip de imagen
- **Voz en dev:** `VOICE_PROVIDER=fal` (Kokoro Spanish) reusa `FAL_API_KEY`; no hace falta ElevenLabs para probar Reels
- **ffmpeg es dependencia de sistema** (no Python) requerida solo para `user_clip_reel` — `transcription_providers.py` la invoca vía `subprocess` para extraer audio antes de transcribir con Whisper
- **Google OAuth `drive.readonly` puede requerir verificación manual de la app** para usuarios externos a tu organización — en dev, agregar el email como "test user" en la pantalla de consentimiento evita el trámite
- **Limitación restante — URLs de clips en wan-effects:** `clip_assets.py` sigue generando `http://localhost:8000/static/...`; Shotstack ya recibe URLs públicas vía `_publicize_edit`, pero fal.ai wan-effects (si `EFFECTS_ENABLED=true`) aún necesita ngrok activo para alcanzar el clip fuente a mitad de pipeline
- **Captions de `user_clip_reel` son por segmento, no por palabra** — granularidad más fina queda para v2
- **LLM debe estar vivo Y caliente o el copy sale genérico:** `get_llm()` devuelve un `OllamaLLM` aunque Ollama esté apagado; si la llamada falla (server caído o cold-start > timeout 180s de `llm.py`), estratega y copywriter atrapan la excepción y caen a `_stub()` → texto de plantilla en la imagen **sin error visible al usuario**. Ollama descarga el modelo tras ~5 min inactivo, así que el cold-start reaparece. Mantener `ollama serve` corriendo y el modelo pre-cargado antes de generar. Fix propuesto (no aplicado): `keep_alive` + timeout de cold-start en `llm.py`
- **Imagen fail-loudly:** fal.ai / SD ya no caen a placeholder silencioso; fallan con `RuntimeError(image_gen_failed:…)`. Placeholders solo con `IMAGE_PROVIDER=mock` o mocks de test
- **Doctrina inbound:** `agents/marketing_agents/knowledge/inbound_marketing.py` se inyecta en `_SYSTEM` de estratega, copywriter y `video_script` (pirámide Entretener → Información → Conexión + `publico_objetivo`)
- **Revisión HITL (parcial):** UI captura notas en `revisionByRunId`; backend `POST /runs/{id}/revise` **no** existe aún
- **Meta OAuth:** redirect URI debe ser path completo (`…/api/auth/callback/meta`); token sin scopes IG → Graph subcode 33 (re-autorizar desde Integraciones)

---

## Deuda conocida (no implementar sin pedido explícito)

1. Canva OAuth — placeholder, no implementado
2. Canva/Figma MCP — plantillas de marca vía MCP
3. Stable Diffusion local — alternativa conservada, no es camino principal; A1111 caído → error explícito (no mock)
4. Video v2 (no implementado) — TikTok (solo Instagram Reels por ahora), música de fondo, captions por palabra (hoy por segmento) para `user_clip_reel`
5. `POST /runs/{id}/revise` — regenerar piezas con notas del dashboard
6. Meta: re-OAuth con scopes IG cuando el token solo tenga `pages_*` / `public_profile`
7. Ollama cold-start — `keep_alive` + timeout (propuesto, no aplicado)

---

## Git

- Rama activa: `main`
- Commits directamente a `main`; no crear ramas salvo petición explícita
- `master` es rama estable; fusionar solo cuando el usuario lo indique
