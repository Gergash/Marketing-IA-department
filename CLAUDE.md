# Marketing DEPA IA — Scope de Proyecto

## Qué es este proyecto

MVP de automatización de marketing con agentes de IA. Flujo: brief (+ manual de marca) → estrategia → copy con QA → diseño visual → aprobación humana → publicación en redes.

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
Strategist (+ brand + inbound)
  → LangGraph [Copywriter ↔ QA]
  → Designer | VideoDesigner | ClipReelDesigner
  → HITL → Publisher (multi-cuenta)
```

Asesor creativo (`advisor.py`) es **fuera** del pipeline: chat vía `POST /api/advisor/chat`.

Doctrina inbound (HubSpot/Cyberclick/…) vive en
`agents/marketing_agents/knowledge/` y se inyecta en Strategist, Copywriter y VideoScriptAgent.
Pirámide: **Entretener → Informacion → Conexion**.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| API | FastAPI + Alembic (Python 3.10) |
| Agentes | LangGraph + LangChain |
| LLM | Ollama / Anthropic / OpenAI / **OpenRouter** — configurable vía `.env` |
| Imágenes | **fal.ai** (principal) + **Venice.ai** + SD / DALL·E |
| Marca | PDF + PaddleOCR + `brand_scan` (paleta/logos) + fonts OFL |
| Video (Reels) | **Shotstack**; escenas `still` o Venice i2v (`VIDEO_SCENE_PROVIDER`) |
| Voz (voiceover) | **fal.ai Kokoro Spanish** (dev) / ElevenLabs / OpenAI TTS |
| Transcripción (clips usuario) | **Whisper** (`whisper-1`) |
| Fuente de clips | Google Drive (OAuth `drive.readonly`) |
| Social | Meta/IG + LinkedIn + **X** OAuth; Go (Meta) + Python nativo (LinkedIn, X) |
| Async | Celery + Redis (default + `-Q video_render`) |
| Scheduler | APScheduler |
| Frontend | React + Vite (+ AdvisorChatBubble) |
| DB | PostgreSQL (Docker host **5433** local; contenedor en prod) |
| Prod VPS | Hostinger KVM 4 + Caddy host — `infra/deploy/vps-hostinger.md` |

---

## Estructura de archivos clave

```
agents/marketing_agents/
  knowledge/            — doctrina verificada (inbound + redes); se inyecta en prompts
  strategist.py         — tipo de post, hook, mensaje base (inbound: atraer→convertir→cerrar→deleitar)
  copywriter.py         — copy + headline/subline; pirámide Entretener→Informacion→Conexion
  graph_copy_qa.py      — bucle LangGraph Copywriter ↔ QA
  quality.py            — reglas de calidad de diseño
  designer.py           — arquetipo + Flux/Venice/SD + composición PIL (+ logo de marca)
  brand_manual.py       — PDF upload, extract texto, active.json
  ocr_paddle.py         — fallback OCR local (PaddleOCR + PyMuPDF)
  brand_scan.py         — paleta dominante + logos embebidos/cabecera
  brand_visual.py       — cues (hex/fuentes/logos) → prompts y arquetipo
  advisor.py            — CreativeAdvisorAgent (chat)
  venice_client.py      — HTTP client Venice.ai (imagen + /image/edit + video queue)
  revision_prompt.py    — notas de revisión + build_scene_edit_prompt (solo escena)
  caption.py            — caption publicable (hashtags + link_url)
  publisher.py          — publicación vía proveedor social
  image_providers.py    — generación, overlay, compose_from_user_asset (edit)
  user_assets.py        — carga y fit de fotos del usuario
  visual_prompt_guards.py — anti-texto en prompts de generación
  layout_archetypes.py  — 5 arquetipos (incl. brand_campaign_piece)
  design_layouts.py     — composición PIL por arquetipo (+ logo)
  video_script.py       — VideoScriptAgent: guion 3-5 escenas
  video_timeline.py     — Timeline/Scene + to_shotstack_edit()
  video_providers.py    — render_video() Shotstack
  voice_providers.py    — synthesize_voice()
  video_designer.py     — VideoDesignerAgent (still o Venice i2v)
  drive_source.py       — Google Drive clips
  transcription_providers.py — Whisper
  clip_assets.py / clip_editor.py / clip_reel_designer.py
  thought_stream.py     — hilo de pensamiento (eventos en vivo + checkpoints interactivos)
  pipeline.py           — MarketingPipeline
  llm.py                — Ollama/Anthropic/OpenAI/OpenRouter (+ keep_alive)
  overlay_text.py       — tipografía OFL + Windows fonts
  social_providers.py   — Meta (Go), LinkedIn y X nativo (Python)
  schemas.py
  image_specs.py        — dimensiones + catálogo de formatos por red (fuente única)
  text_contrast.py      — color de texto según luminancia del fondo
  visual_prompt_guards.py — sufijo/negativos anti-texto para fal/Venice/SD
  venice_video_models.py  — aliases UI/.env → model IDs Venice
  knowledge/            — doctrina inbound

gateway/app/
  api/routes.py          — endpoints principales
  api/auth_social.py     — OAuth Meta/LinkedIn/Google (2.0) + X (1.0a); multi-cuenta + /auth/accounts
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

skaffold.yaml           — build de las 3 imágenes + deploy vía overlays kustomize
clouddeploy.yaml        — pipeline Cloud Deploy staging → prod (prod requiere aprobación)
k8s/base/               — manifiestos comunes (api, worker, video-worker, go-publisher)
k8s/overlays/{dev,staging,prod}/ — réplicas y APP_ENV/SHOTSTACK_ENV por entorno
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
| `brand_campaign_piece` | Manual de marca activo (logo + foto full-bleed + tipografía centrada) |
| `typographic_poster` | Promocional / ventas |
| `minimal_conceptual` | Informativo |
| `editorial_infographic` | Educativo / branding (sin manual) |
| `cinematic_hero` | Storytelling / entretenimiento |

Referencia visual: `docs/references/README.md`. Fonts OFL: `static/fonts/README.md`.

---

## Dimensiones de imagen por plataforma

| Plataforma/Formato | Dimensión | Aspecto |
|--------------------|-----------|---------|
| Instagram/Facebook feed | 1080×1350 | 4:5 |
| Stories/Reels (imagen) | 1080×1920 (~810×1440 fal) | 9:16 |
| Reel (video, `content_format=reel`) | 1080×1920, 30fps | 9:16 |
| Reel con clips propios (`content_format=user_clip_reel`) | 1080×1920, 30fps | 9:16 (duración 6-60s, no 15-30s del reel generado) |
| LinkedIn feed | 1200×627 | — |
| X (Twitter) feed | 1200×675 | 16:9 |
| TikTok (imagen/video) | 1080×1920 | 9:16 |
| Universal (`content_format=universal`) | 1080×1080 | 1:1 |

fal.ai escala proporcionalmente si altura > 1440px.

---

## Config `.env` típica en dev

```env
IMAGE_PROVIDER=venice              # evaluación / foto real; o fal | stable_diffusion
FAL_API_KEY=...                    # si usas fal
FAL_MODEL=fal-ai/flux-pro/v1.1
VENICE_API_KEY=...
VENICE_API_BASE=https://api.venice.ai/api/v1
VENICE_IMAGE_MODEL=gpt-image-2
VENICE_IMAGE_RESOLUTION=2K
VENICE_IMAGE_EDIT_MODEL=gpt-image-2-edit
# No enviar quality a /image/edit (API 400). Ver docs/foto-real-venice-edit.md
VIDEO_SCENE_PROVIDER=still         # o venice
OCR_PROVIDER=paddle
OCR_LANG=es
OCR_USE_GPU=true
OCR_MIN_TEXT_CHARS=40
FAL_IMG2IMG_MODEL=fal-ai/flux/dev/image-to-image
FAL_IMG2IMG_STRENGTH=0.72
VIDEO_PROVIDER=shotstack
SHOTSTACK_API_KEY=...
SHOTSTACK_ENV=stage
VOICE_PROVIDER=fal
VOICE_LANGUAGE=es
FAL_TTS_MODEL=fal-ai/kokoro/spanish
FAL_TTS_VOICE=ef_dora
STT_PROVIDER=whisper
EFFECTS_ENABLED=false
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
THOUGHTS_ENABLED=true          # hilo de pensamiento de los agentes
THOUGHTS_TTL_SECONDS=7200
THOUGHTS_CHECKPOINT_TIMEOUT_SECONDS=180
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1
OLLAMA_KEEP_ALIVE=30m
LLM_TIMEOUT_SECONDS=300
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/marketing_mvp
REDIS_URL=redis://localhost:6379/0
SOCIAL_PROVIDER=meta
GO_PUBLISHER_URL=http://localhost:8088
PUBLIC_IMAGE_BASE_URL=https://TU-NGROK
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_API_VERSION=202401     # header LinkedIn-Version de la API /rest
# Deben estar CONCEDIDOS en la pestaña Auth de la app; si no, LinkedIn rechaza todo el consentimiento.
# Sin el producto "Sign In with LinkedIn using OpenID Connect": r_basicprofile w_member_social
LINKEDIN_SCOPES=openid profile w_member_social
```

**Nunca commitear `.env`.**

**Foto real:** subir en dashboard + Alterar IA → guía [`docs/foto-real-venice-edit.md`](docs/foto-real-venice-edit.md). Tras cambiar `.env`, preferí **un solo** Uvicorn (evitar workers zombi en `:8000`).

**Marca:** subir PDF en el dashboard; requiere `pymupdf` (+ PaddleOCR si `OCR_PROVIDER=paddle`).

**Reel es async-only:** `content_format=reel|user_clip_reel` → `POST /api/runs/async` + segundo worker:

```bash
python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render
```

Tras cambiar `.env` o código de video, **reinicia el worker**.

**`user_clip_reel`** requiere `ffmpeg` en PATH y `drive_folder_id`.

---

## Cómo levantar el stack (7-8 terminales)

Ver `infra/arranque-stack.md` (local).  
**Producción en Hostinger KVM 4 (junto a InsightFlow):** `infra/deploy/vps-hostinger.md` — un Caddy en el host, compose sin 80/443, puertos loopback.  
**Integración redes (estado del proceso):** `infra/deploy/proceso-integracion-redes.md` · Meta: `meta-oauth-production.md` · X: `x-oauth-production.md` · TikTok: `tiktok-app-review.md`.

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
cd microservices/social-publisher-go && go run ./cmd/server

# 7 - ngrok (Meta + assets locales)
ngrok http 8000
```

---

## API endpoints relevantes

- `POST /api/briefs/upload-asset` — foto usuario
- `POST /api/briefs/upload-brand-manual` — PDF marca
- `GET/DELETE /api/briefs/brand-manual` — manual activo
- `POST /api/advisor/chat` — asesor creativo
- `POST /api/runs/sync` / `/async` — pipeline (`content_format`, `image_provider`, `social_account_id`, `link_url`, `cta_on_image`, …)
- `POST /api/runs/{id}/approve` / `/reject` / `/revise`
- `GET /api/thoughts/{trace_id}?since=N` — hilo de pensamiento de los agentes (polling)
- `POST /api/thoughts/{trace_id}/reply` — respuesta del usuario en un checkpoint (`continue` | `adjust` | `cancel`)
- `GET /api/auth/accounts` / `DELETE /api/auth/accounts/{id}`
- `POST /api/campaigns/{id}/fire`
- `GET /api/image/archetypes` / `/image/providers` / `/image/formats` (formatos válidos por red)

---

## Tests

```bash
pytest tests/ -v
```

~**271 tests** collected. Archivos clave además de pipeline/video/clips:

- `tests/test_brand_and_advisor.py`, `test_brand_scan.py`, `test_brand_visual.py`
- `tests/test_venice.py`, `test_venice_edit.py`, `test_revision_prompt.py`, `test_premium_fonts.py`, `test_caption.py`
- `tests/test_revise_run.py`, `test_multi_account.py`, `test_llm_keep_alive.py`
- `tests/test_format_normalization.py` (formatos por red + universal), `test_thought_stream.py`, `test_text_contrast_and_video_models.py`, `test_linkedin_native.py`

3 fallos preexistentes en `test_venice.py` / `test_video_timeline_clips.py` (estructura del edit Shotstack).

Estado canónico: [`estado-actual.txt`](estado-actual.txt).  
NotebookLM: [`docs/notebooklm/Marketing-DEPA-IA-fuente-completa.md`](docs/notebooklm/Marketing-DEPA-IA-fuente-completa.md).

---

## Decisiones arquitectónicas fijas

- **ComfyUI: descartado** (GPU local insuficiente para Flux; usar fal.ai / Venice)
- **Brand book manda:** texto + paleta + logos del PDF tienen prioridad sobre plantillas genéricas (evitar look amarillo/blanco por defecto)
- **Prometheus:** `PROMETHEUS_ENABLED=true` → `/metrics`; off en dev
- **Go publisher:** no duplicar lógica Meta en Python si Go ya intentó
- **LinkedIn = solo Python:** el sidecar Go cubre únicamente Meta. LinkedIn usa la API versionada `/rest/images` + `/rest/posts` en `social_providers.py` (nunca `/v2/assets` ni `/v2/ugcPosts`, deprecados). Solo imagen y solo perfil personal
- **Anti-duplicados IG:** error 9007 = container no `FINISHED`
- **ngrok**: Meta + assets locales; Reels fal → Shotstack vía `fal.media`
- **Reel async-only** + cola `video_render` + **sin autoretry** en video
- **Contrato Shotstack:** overlays = clips `TitleAsset`, nunca propiedad `title_asset`
- **ffmpeg** solo para `user_clip_reel`
- **LLM stub silencioso** si Ollama apagado — mitigado con `keep_alive`/timeout; falta error en UI
- **Imagen fail-loudly** (fal/Venice/SD); mock solo con `IMAGE_PROVIDER=mock`
- **Foto real + edit:** tipografía solo Pillow; Venice `/image/edit` **sin** campo `quality` (schema 400); un solo proceso en `:8000`
- **HITL revise** nunca publica; multi-cuenta vía `social_account_id`
- **Formatos por red:** catálogo único en `image_specs.py` (`_NETWORK_FORMATS`), servido por `GET /api/image/formats`; el dashboard nunca hardcodea dimensiones
- **`content_format=universal`** = 1080×1080 idéntico en todas las redes (para publicar la misma pieza en varias); se comporta como `feed` en layout y publicación
- **TikTok:** generación sí; publish tras App Review. **X:** publish nativo (OAuth 1.0a)

---

## Deuda conocida (no implementar sin pedido explícito)

1. Canva OAuth / Canva-Figma MCP
2. Stable Diffusion local — alternativa; A1111 caído → error explícito
3. Video v2 — música, captions por palabra
4. TikTok fase 2 (auditoría app)
5. Meta: re-OAuth scopes IG; ngrok dominio fijo
6. Revise v2 — historial de versiones
7. CI/CD — Skaffold/Cloud Deploy sin GKE real
8. Fallback LLM → propagar a UI
9. Unlimited-OCR descartado (VRAM); PaddleOCR es el camino OCR

---

## Git

- Rama activa: `main`
- Commits directamente a `main`; no crear ramas salvo petición explícita
- `master` es rama estable; fusionar solo cuando el usuario lo indique
