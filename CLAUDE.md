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
| Social | Meta/IG OAuth + Go publisher; LinkedIn; mocks |
| Async | Celery + Redis |
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
| Stories/Reels | 1080×1920 (~810×1440 fal) | 9:16 |
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
- `POST /api/runs/sync` / `/async` — ejecutar pipeline (`user_asset_url`, `alter_image_with_ai`, `visual_instructions`, `archetype_override`)
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

---

## Decisiones arquitectónicas fijas

- **ComfyUI: descartado** (GPU local insuficiente para Flux; usar fal.ai)
- **Prometheus:** activable con `PROMETHEUS_ENABLED=true`; no es prioridad en dev
- **Go publisher:** no duplicar lógica de publicación Meta en Python si Go ya intentó
- **Anti-duplicados IG:** error 9007 indica container no `FINISHED` — manejar sin reintentar ciegamente
- **ngrok obligatorio** para que Meta acceda a las imágenes generadas

---

## Deuda conocida (no implementar sin pedido explícito)

1. Canva OAuth — placeholder, no implementado
2. Canva/Figma MCP — plantillas de marca vía MCP
3. Stable Diffusion local — alternativa conservada, no es camino principal

---

## Git

- Rama activa: `main`
- Commits directamente a `main`; no crear ramas salvo petición explícita
- `master` es rama estable; fusionar solo cuando el usuario lo indique
