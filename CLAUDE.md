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

---

## Stack

| Capa | Tecnología |
|------|-----------|
| API | FastAPI + Alembic (Python 3.10) |
| Agentes | LangGraph + LangChain |
| LLM | Ollama / Anthropic / OpenAI — configurable vía `.env` |
| Imágenes | **fal.ai (Flux Pro)** — principal; DALL·E y SD como alternativas |
| Video (Reels) | **Shotstack** (block-and-poll) — principal; JSON2Video documentado, no implementado |
| Voz (voiceover) | **ElevenLabs** — principal; OpenAI TTS como alternativa; español por defecto |
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
  strategist.py         — tipo de post, hook, mensaje base
  copywriter.py         — copy + headline/subline para imagen
  graph_copy_qa.py      — bucle LangGraph Copywriter ↔ QA
  quality.py            — reglas de calidad de diseño
  designer.py           — arquetipo editorial + prompt Flux + composición PIL
  publisher.py          — publicación vía proveedor social
  image_providers.py    — generación, overlay post-proceso e img2img
  user_assets.py        — carga y fit de fotos del usuario
  layout_archetypes.py  — 4 arquetipos editoriales
  design_layouts.py     — composición PIL por arquetipo
  video_script.py       — VideoScriptAgent: guion 3-5 escenas, hook/CTA, banda 15-30s
  video_timeline.py     — contrato Timeline/Scene/VoiceoverTrack (Pydantic) + to_shotstack_edit()
  video_providers.py    — render_video(): Shotstack block-and-poll / mock
  voice_providers.py    — synthesize_voice(): ElevenLabs / OpenAI TTS / mock
  video_designer.py     — VideoDesignerAgent: escenas fal.ai + voz + Timeline + render
  drive_source.py       — OAuth Google Drive: listar y descargar clips de una carpeta
  transcription_providers.py — transcribe_clips(): Whisper (ffmpeg extrae audio) / mock
  clip_assets.py        — clip_public_url(): mapea path local de clip a URL servida
  clip_editor.py         — ClipEditorAgent: selección hook-scored de segmentos (banda 6-60s)
  clip_reel_designer.py — ClipReelDesigner: Drive → transcripción → selección → [efecto] → Timeline → render

gateway/app/
  api/routes.py         — endpoints principales
  api/auth_social.py    — OAuth Meta/LinkedIn
  core/settings.py      — configuración (carga .env)
  services/pipeline_service.py — orquestación del pipeline
  schemas/contracts.py  — Pydantic schemas entrada/salida

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
SHOTSTACK_API_KEY=...
SHOTSTACK_ENV=stage
VIDEO_MAX_WAIT_SECONDS=600
VIDEO_FPS=30
VOICE_PROVIDER=elevenlabs
VOICE_LANGUAGE=es
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
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
PUBLIC_IMAGE_BASE_URL=https://TU-NGROK
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
```

**Nunca commitear `.env`.**

**Reel es async-only:** `content_format=reel` (y también `user_clip_reel`) requiere `POST /api/runs/async` (se rechaza con 422 en `/runs/sync`) y un **segundo worker Celery** en la cola dedicada:

```bash
celery -A workers.celery_app worker -Q video_render --loglevel=info
```

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

# 4 - Worker Celery
celery -A workers.celery_app worker --loglevel=info

# 5 - Frontend
cd frontend && npm run dev

# 6 - Go publisher (solo al publicar)
cd microservices/social-publisher-go && go run .

# 7 - ngrok (solo al publicar en IG; actualizar PUBLIC_IMAGE_BASE_URL)
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
- `tests/test_layout_archetypes.py` — specs 4:5, fal scaling
- `tests/test_design_layouts.py` — composición PIL: 4 layouts, fallback
- `tests/test_user_assets.py` — foto usuario + overlay sin fal
- `tests/test_linkedin_native.py` — LinkedIn con imagen (mock)
- `tests/test_video_timeline.py` — contrato Timeline/Scene, `to_shotstack_edit()`, clamp de duración
- `tests/test_voice_providers.py` — `synthesize_voice` (mock/ElevenLabs/OpenAI, default español)
- `tests/test_video_providers.py` — `render_video` (mock/Shotstack poll, fallo y timeout distintos)
- `tests/test_video_designer.py` — `VideoDesignerAgent.run` end-to-end mockeado
- `tests/test_video_pipeline.py` — `MarketingPipeline.run(content_format="reel")` end-to-end + regresión feed
- `tests/test_pipeline_service_video.py` — `_media_url` y persistencia de `video_url`
- `tests/test_drive_source.py` — OAuth Google Drive: listar/descargar clips, sanitización de nombre de archivo
- `tests/test_transcription_providers.py` — Whisper mockeado, chunking >25MB con offset-correction
- `tests/test_clip_editor.py` / `tests/test_clip_assets.py` — selección hook-scored banda 6-60s, stub determinístico
- `tests/test_clip_reel_designer.py` — `ClipReelDesigner` end-to-end mockeado, wan-effects (éxito/degradación), reset de trim tras efecto, captions multi-segmento
- `tests/test_contracts_user_clip_reel.py` — validación de `RunRequest` (`drive_folder_id` obligatorio) y límite de columna

---

## Decisiones arquitectónicas fijas

- **ComfyUI: descartado** (GPU local insuficiente para Flux; usar fal.ai)
- **Prometheus:** activable con `PROMETHEUS_ENABLED=true` → `/metrics` (compatible con FastAPI 0.115); off en dev por defecto
- **Go publisher:** no duplicar lógica de publicación Meta en Python si Go ya intentó
- **Anti-duplicados IG:** error 9007 indica container no `FINISHED` — manejar sin reintentar ciegamente
- **ngrok obligatorio** para que Meta acceda a las imágenes generadas
- **Reel es async-only:** `content_format="reel"` (y `user_clip_reel`) se rechaza con 422 en `/runs/sync`; corre solo vía `/runs/async` en la cola Celery dedicada `video_render` — requiere levantar un **segundo worker** (`celery -A workers.celery_app worker -Q video_render`) además del worker default
- **Video sin retries:** la tarea `execute_video_pipeline_task` usa el `celery.Task` base plano (sin `autoretry_for`) para no re-renderizar video ante errores transitorios (costo/duplicados)
- **ffmpeg es dependencia de sistema NUEVA** (no Python) requerida solo para `user_clip_reel` — `transcription_providers.py` la invoca vía `subprocess` para extraer audio antes de transcribir con Whisper
- **Google OAuth `drive.readonly` puede requerir verificación manual de la app** para usuarios externos a tu organización — en dev, agregar el email como "test user" en la pantalla de consentimiento evita el trámite
- **Limitación conocida — URLs de clips/video no se sustituyen a `PUBLIC_IMAGE_BASE_URL` a mitad de pipeline:** `clip_assets.py` y `video_providers.py` generan siempre `http://localhost:8000/static/...`; la sustitución a la URL pública solo ocurre en el paso final de publicación (`_publish_via_go`). Si fal.ai (wan-effects) o Shotstack necesitan alcanzar el clip/video desde fuera de la máquina, `PUBLIC_IMAGE_BASE_URL` (ngrok) debe estar configurado o el fetch remoto falla
- **Captions de `user_clip_reel` son por segmento, no por palabra** — granularidad más fina queda para v2

---

## Deuda conocida (no implementar sin pedido explícito)

1. Canva OAuth — placeholder, no implementado
2. Canva/Figma MCP — plantillas de marca vía MCP
3. Stable Diffusion local — alternativa conservada, no es camino principal
4. Video v2 (no implementado) — TikTok (solo Instagram Reels por ahora), música de fondo, captions por palabra (hoy por segmento) para `user_clip_reel`

---

## Git

- Rama activa: `main`
- Commits directamente a `main`; no crear ramas salvo petición explícita
- `master` es rama estable; fusionar solo cuando el usuario lo indique
