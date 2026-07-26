# Arquitecturas de Agentes Autónomos y Protocolos de Contexto para la Automatización Integral de Ecosistemas Creativos y Gestión de Redes Sociales

Plataforma avanzada de automatización de marketing digital basada en agentes de IA.

## Capacidades

- Generación automática de diseños gráficos
- Creación programática de videos
- Redacción de guiones y contenido optimizado
- Publicación y respuesta automática en redes sociales
- Integración de herramientas mediante MCP (Model Context Protocol)
- Orquestación de agentes especializados (copywriter, diseñador, analista, community manager)

## Stack Tecnológico

| Capa | Tecnología |
|---|---|
| Orquestación IA | LangGraph + LangChain |
| Modelos IA | LLMs vía API (OpenAI, Anthropic, Ollama) |
| Backend API | FastAPI (Python 3.10) |
| Microservicios | Go |
| Base de datos | PostgreSQL + Redis |
| Migraciones | Alembic |
| Cola de tareas | Celery |
| Frontend | React + Vite |
| Contenido visual | fal.ai (Flux Pro) + Pillow overlay + foto usuario (Design-as-Code) |
| Video (Reels) | Shotstack (block-and-poll, `stage`/`v1`) + fal.ai Kokoro TTS (voz; ElevenLabs/OpenAI alt) |
| Contenedores | Docker |

## Estado del roadmap

- **Paso 1** Happy path local: API + frontend sin fricciones (CORS + proxy Vite)
- **Paso 2** PostgreSQL + Alembic: Docker Compose con healthchecks, migraciones versionadas
- **Paso 3** APIs reales: LLMs (Anthropic/OpenAI/Ollama), imagen (fal.ai/Flux, SD, DALL·E), social (Meta/LinkedIn nativo vía OAuth + Go)
- **Paso 4** Seguridad: Auth real, secrets, human-in-the-loop
- **Paso 5** LangGraph: bucle **Copywriter ↔ QA** con trazabilidad (`copy_qa_trace`); resto del pipeline lineal — ver [`agents/PIPELINE.md`](agents/PIPELINE.md). Doctrina inbound en `agents/marketing_agents/knowledge/` (Entretener→Informacion→Conexion).
- **Paso 6** 🟡 Go/infra: sidecar Go operativo; MCP connect en stdio; Kubernetes esqueleto
- **Paso 7** Video-as-Code (Reels): `content_format=reel` (script → escenas fal.ai + voz fal → timeline TitleAsset → Shotstack). Assets fal van a Shotstack como URLs `fal.media`; ngrok/`PUBLIC_IMAGE_BASE_URL` sigue siendo necesario para **Meta** y assets locales. Async-only, cola Celery `video_render`.
- **Paso 8** Reel con clips del usuario: `user_clip_reel` (Drive → Whisper → hook-scored → captions → wan-effects opcional → Shotstack/Go). Pendiente v2: TikTok, música, captions por palabra.
- **Paso 9** 🟡 Revisión de piezas: UI **Solicitar cambios** en dashboard (stub); backend `POST /runs/{id}/revise` pendiente.

Estado narrativo detallado: [`estado-actual.txt`](estado-actual.txt) (actualizado 2026-07-25).

## Estructura

```
gateway/        API Gateway FastAPI (sync + async)
agents/         Agentes Python + `PIPELINE.md` (orquestación lineal vs LangGraph)
workers/        Worker Celery para ejecución en background
microservices/  social-publisher-go: adaptador de publicación en Go
frontend/       Dashboard React/Vite
infra/          docker-compose.yml (Postgres + Redis)
alembic/        Migraciones de base de datos
```

---

## Requisito de Python

El proyecto está pensado para **Python 3.10**. Hay un archivo `.python-version` para **pyenv**. Las imágenes Docker usan `python:3.10-slim`.

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

### Dependencia de sistema: ffmpeg (requerida para `content_format=user_clip_reel`)

El flujo de Reel con clips del usuario extrae el audio de cada clip vía `subprocess` antes de transcribirlo con Whisper. Instala `ffmpeg` y verifica que esté en el `PATH`:

```bash
# Windows (choco): choco install ffmpeg
# macOS (brew):    brew install ffmpeg
# Debian/Ubuntu:   sudo apt-get install ffmpeg
ffmpeg -version
```

No es necesario para el resto del pipeline (feed/story/reel generado).

## Proveedores de imagen alternativos (legacy)

> **Proveedor principal: `IMAGE_PROVIDER=fal`** — ver sección 3B.
> **ComfyUI: descartado** (GPU local insuficiente para Flux; usar fal.ai en su lugar).

**Stable Diffusion local (Automatic1111 / Forge)** — alternativa sin GPU cloud:

Con `IMAGE_PROVIDER=stable_diffusion` en `.env`:

1. Arranca **Automatic1111 WebUI** con la API activa (por ejemplo `--api`, puerto por defecto 7860).
2. Coloca el checkpoint en `models/Stable-diffusion/` y anota el nombre **exacto** como aparece en el desplegable del WebUI.
3. Configura `STABLE_DIFFUSION_URL` (típicamente `http://127.0.0.1:7860/sdapi/v1/txt2img`) y `STABLE_DIFFUSION_CHECKPOINT` (p. ej. `Realistic_Vision_V5.1_fp16-no-ema.safetensors` si ese es el nombre del archivo en disco).

Cada petición `txt2img` envía `override_settings.sd_model_checkpoint` para forzar ese modelo.

## Paso 1 — Happy path local (SQLite, sin Docker)

Desde la **raíz del repositorio**. No requiere Docker: la API usa SQLite por defecto. Activa el venv e instala dependencias como en **Requisito de Python** antes de los comandos siguientes.

**Terminal 1 — API**

```bash
python -m uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — Dashboard**

```bash
cd frontend && npm install && npm run dev
```

Abre http://localhost:5173. El frontend en dev usa **proxy Vite** (`/api` → `http://127.0.0.1:8000`).

**Async (Celery + Redis)** — requiere Redis levantado:

```bash
docker compose -f infra/docker-compose.yml up -d redis
python -m celery -A workers.celery_app.celery_app worker -l info
```

En **Windows PowerShell** (si `celery` no se reconoce en PATH):

```powershell
.\.venv\Scripts\python.exe -m celery -A workers.celery_app.celery_app worker -l info
```

`workers/celery_app.py` fuerza `worker_pool=threads` (4 hilos) en Windows para evitar `PermissionError [WinError 5]` del pool `prefork`.

---

## Paso 2 — PostgreSQL + Alembic

### Levantar la base de datos

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

Espera el healthcheck (`pg_isready`). Verifica con:

```bash
docker compose -f infra/docker-compose.yml ps
```

### Configurar el entorno

```bash
copy .env.example .env      # Windows
# cp .env.example .env      # Linux/macOS
```

`DATABASE_URL` en `.env` apunta al Postgres del **Compose en el puerto host 5433** (evita choque con un PostgreSQL instalado en el sistema que suele usar 5432):

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/marketing_mvp
```

Si tras `docker compose ... up -d postgres` ves `FATAL: password authentication failed for user postgres`, casi siempre estás conectando al Postgres **nativo** (puerto 5432), no al contenedor: revisa que `DATABASE_URL` use `:5433` o detén el servicio local de PostgreSQL.

### Aplicar migraciones

```bash
python -m pip install -r requirements.txt   # incluye alembic
python -m alembic upgrade head
```

En **Windows (PowerShell)**, si `alembic` no se reconoce, usa siempre `python -m alembic ...` (o `.\.venv\Scripts\python.exe -m alembic ...` con tu venv).

Esto crea todas las tablas y columnas versionadas (`briefs`, `agent_runs` incluye `content_format` feed/story, `generated_assets`, `publications`, `campaign_schedules`).

### Iniciar la API contra Postgres

```bash
python -m uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000
```

Con `DATABASE_URL` apuntando a Postgres, la API **no ejecuta** `create_all` — Alembic es la única fuente de verdad para el esquema.

### Flujo de trabajo con Alembic

| Acción | Comando |
|---|---|
| Aplicar todas las migraciones | `python -m alembic upgrade head` |
| Ver migración actual | `python -m alembic current` |
| Ver historial | `python -m alembic history` |
| Revertir última migración | `python -m alembic downgrade -1` |
| Generar nueva migración (auto) | `python -m alembic revision --autogenerate -m "descripcion"` |

> **Importante:** después de modificar modelos en `gateway/app/models/entities.py`, genera siempre una nueva migración con `--autogenerate` y revisa el archivo generado antes de hacer `upgrade head`.

### Stack completo (Postgres + Redis + Worker + Frontend + Go + ngrok)

Guía paso a paso con rutas Windows: [`infra/arranque-stack.md`](infra/arranque-stack.md)

```bash
# 1. Infraestructura (desde la raíz del repo)
docker compose -f infra/docker-compose.yml up -d

# 2. Migraciones (primera vez o tras cambios de esquema)
python -m alembic upgrade head

# 3. Verificar Ollama
curl http://localhost:11434/api/tags

# 4. API
python -m uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000

# 5. Worker Celery (otro terminal, misma raíz, venv activado)
python -m celery -A workers.celery_app.celery_app worker -l info

# 6. Frontend (otro terminal)
cd frontend && npm run dev

# 7. Go publisher — solo al aprobar/publicar en Instagram (otro terminal)
cd microservices/social-publisher-go && go run ./cmd/server

# 8. ngrok — solo al publicar en Meta (túnel al API :8000)
cd tests/ngrok-v3-stable-windows-amd64 && ./ngrok.exe http 8000
# Copiar URL https → PUBLIC_IMAGE_BASE_URL en .env → reiniciar Uvicorn
```

Dashboard: http://localhost:5173

---

## Paso 3 — APIs reales

Todos los agentes tienen **fallback automático a stubs mockeados** si no hay API key configurada. El pipeline siempre funciona; las keys activan las integraciones reales.

### 3A — LLMs (estrategia y copywriting)

```env
# .env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001   # más rápido y económico; cambiar a claude-sonnet-4-6 para mayor calidad
ANTHROPIC_API_KEY=sk-ant-...
```

O con OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Si `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` están vacías, los agentes usan texto estático (stub).

> **Gotcha — texto genérico en las imágenes:** si el LLM no responde, estratega y copywriter caen a un **stub** de plantilla y el copy sale genérico **sin error visible**. Con `LLM_PROVIDER=ollama`, esto pasa si `ollama serve` está apagado o si la **primera** llamada hace timeout (cold-start del modelo > 180s). Ollama descarga el modelo tras ~5 min inactivo, así que el cold-start reaparece. Solución: mantén `ollama serve` corriendo y el modelo pre-cargado antes de generar (`ollama run llama3.1 ""`), o usa un proveedor cloud (`LLM_PROVIDER=anthropic`). Verifica en los logs que **no** aparezcan `strategist.using_stub` / `strategist.llm_error` / `copywriter.llm_error`.

### 3B — Imagen (diseño de posts)

**fal.ai — Flux Pro** (proveedor principal recomendado, sin GPU local):

Genera imágenes de calidad profesional vía API. Requiere cuenta en fal.ai (registro gratuito, $1 de crédito inicial ≈ 20 imágenes).

```env
IMAGE_PROVIDER=fal
FAL_API_KEY=tu_key_de_fal.ai
FAL_MODEL=fal-ai/flux-pro/v1.1   # o fal-ai/flux/schnell para mayor velocidad
```

Instalación del SDK (una vez):

```bash
pip install fal-client
# ya incluido en requirements.txt
```

El pipeline descarga la imagen generada, aplica overlay de copy/CTA con Pillow y la guarda en `static/images/fal_<uuid>.png`. Logs esperados: `image.fal_generated` → `image.fal_saved`.

**Foto del usuario (Design-as-Code):** sube JPEG/PNG/WebP con `POST /api/briefs/upload-asset` → `static/uploads/`. En el run, pasa `user_asset_url`. Sin toggle de IA: la foto queda como capa base y solo se aplica overlay editorial. Con `alter_image_with_ai: true` + `visual_instructions`: fal img2img (`FAL_IMG2IMG_MODEL`) y luego overlay; el run sigue en `pending_approval`.

```env
FAL_IMG2IMG_MODEL=fal-ai/flux/dev/image-to-image
FAL_IMG2IMG_STRENGTH=0.72
```

**DALL-E 3** (requiere `OPENAI_API_KEY`):

```env
IMAGE_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

**Canva API** (requiere OAuth — ver comentarios en `agents/marketing_agents/image_providers.py`):

```env
IMAGE_PROVIDER=canva
CANVA_CLIENT_ID=...
CANVA_CLIENT_SECRET=...
CANVA_TEMPLATE_ID=...
```

Si `IMAGE_PROVIDER=mock` (por defecto), se genera una URL placeholder de dummyimage.com.

### 3C — Publicación en redes sociales

Publicación **nativa** vía OAuth (dashboard → Integraciones) y sidecar Go en `:8088`. No hay proveedor omnicanal de terceros.

**LinkedIn** (OAuth + imagen):

```env
SOCIAL_PROVIDER=linkedin
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=
LINKEDIN_REDIRECT_URI=http://localhost:8000/api/auth/callback/linkedin
GO_PUBLISHER_URL=http://localhost:8088
```

Conecta la cuenta en el dashboard. Publicación con imagen: `registerUpload` → PUT → `ugcPosts` (Go o Python).

**Meta / Instagram Business** (publicación en feed o **historia** con Graph API; imagen en URL HTTPS pública):

```env
SOCIAL_PROVIDER=meta
META_PAGE_ACCESS_TOKEN=...
INSTAGRAM_BUSINESS_ACCOUNT_ID=...
# Opcional: META_APP_ID, META_APP_SECRET, GRAPH_API_VERSION=v21.0
```

- Comprueba credenciales sin exponer secretos: `GET /api/social/publish-status`.
- Al crear un run (`POST /api/runs/sync` o `/async`), envía `content_format`: `"feed"`, `"story"` o `"reel"`, y opcionalmente `user_asset_url`, `alter_image_with_ai`, `visual_instructions`, `archetype_override`.
- **Historias** vía API oficial requieren `SOCIAL_PROVIDER=meta` e Instagram profesional.
- Las **historias** de Instagram suelen pedir imagen **9:16** y URL **HTTPS** accesible públicamente (`PUBLIC_IMAGE_BASE_URL` con ngrok en dev).
- **Reels** (`content_format="reel"`) son **async-only**: `/runs/sync` responde `422`; usa siempre `/runs/async` con un segundo worker Celery en la cola `video_render` (`python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render`). Requiere `VIDEO_PROVIDER`/`SHOTSTACK_API_KEY` (`SHOTSTACK_ENV=stage` para sandbox) y `VOICE_PROVIDER=fal` (o elevenlabs). Con fal.ai, Shotstack descarga fondos/voz desde `fal.media`; `PUBLIC_IMAGE_BASE_URL` (ngrok) es obligatorio para **publicar en Meta** y para assets locales (overlays / `user_clip_reel`). Ver sección **PASO 3D** en `.env.example`.
- **Reel con clips del usuario** (`content_format="user_clip_reel"`) es también **async-only** y requiere `drive_folder_id` en el request (422 si falta o si se usa `/runs/sync`). Requiere además: `ffmpeg` instalado en el host (dependencia de sistema NUEVA — se invoca vía `subprocess` para extraer el audio de cada clip antes de transcribir), credenciales OAuth de Google (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REDIRECT_URI`) y, para el scope `drive.readonly` en producción con usuarios externos a tu organización, Google puede exigir un **paso manual de verificación de la app** (agrega tu email en modo "Testing" en la pantalla de consentimiento OAuth para evitarlo en dev). Los captions son **por segmento** (no por palabra) en esta versión — granularidad más fina queda para v2.
  - **URLs públicas:** antes del submit a Shotstack, `video_providers._publicize_edit` reescribe `http://localhost:8000` → `PUBLIC_IMAGE_BASE_URL`. Si `EFFECTS_ENABLED=true`, fal.ai wan-effects aún necesita ngrok para alcanzar clips locales a mitad de pipeline.
- **HITL:** Aprobar / Rechazar en dashboard. **Solicitar cambios** captura notas en UI (stub); regeneración vía API aún no cableada.
- **Meta Instagram:** OAuth desde Integraciones con redirect URI **completo** (`…/api/auth/callback/meta`) y scopes `instagram_basic`, `instagram_content_publish`. Sin ellos, Graph API responde subcode 33.

Si `SOCIAL_PROVIDER=mock` (por defecto), la publicación genera una URL falsa sin llamadas externas.

---


## Prometheus — Métricas en producción

Prometheus se activa con `PROMETHEUS_ENABLED=true`. En desarrollo viene desactivado (`false`) para reducir ruido local; el stack actual (FastAPI 0.115 + `prometheus-fastapi-instrumentator` 7.x) es compatible.

**Para activar en producción:**

```env
PROMETHEUS_ENABLED=true
```

La inicialización está protegida con `try/except`: si la librería no está instalada o hay un conflicto de versiones, la API arranca igual (con un warning en logs). Para instalar:

```bash
pip install --upgrade prometheus-fastapi-instrumentator
```

Las métricas quedan expuestas en `GET /metrics` y se conectan a Grafana u otro dashboard de observabilidad.

---

## Paso 6 — Escalado e infraestructura Go (Post-MVP)

### 6.1 Endurecimiento de tareas en background (Celery)

- Configuracion reforzada en `workers/celery_app.py`:
  - `task_acks_late=True`
  - `task_reject_on_worker_lost=True`
  - `worker_prefetch_multiplier=1`
  - `broker_connection_retry_on_startup=True`
  - `broker_transport_options.visibility_timeout=3600`
- Health task minima: `workers.healthcheck_task`.
- Health endpoints en API:
  - `GET /api/health/background` (broker Redis + workers Celery)

### 6.2 Capa de conectividad Go (mcp-golang)

- Nuevo servidor MCP: `microservices/mcp-connect-go/` (stdio).
- Base para mover integraciones pesadas de Python a Go:
  - `health_status`
  - `publish_social_stub`

Run local:

```bash
cd microservices/mcp-connect-go
go mod tidy
go run ./cmd/server
```

### 6.3 Contenedores para plataforma completa

Archivo: `infra/docker-compose.platform.yml`

```bash
docker compose -f infra/docker-compose.platform.yml up -d --build
```

Incluye `postgres`, `redis`, `api`, `worker` y `go-publisher`, todos con healthchecks.

Nota: `mcp-connect-go` usa transporte stdio (no HTTP), por lo que no se expone como servicio de red en Compose/K8s en esta etapa.

### 6.4 Preparación Kubernetes

Manifiestos base en `k8s/base/`:
- `namespace.yaml`
- `configmap.yaml`
- `secret.example.yaml`
- `api-deployment.yaml`
- `worker-deployment.yaml`
- `go-publisher-deployment.yaml`

Aplicación rápida:

```bash
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/configmap.yaml
kubectl apply -f k8s/base/secret.example.yaml
kubectl apply -f k8s/base/api-deployment.yaml
kubectl apply -f k8s/base/worker-deployment.yaml
kubectl apply -f k8s/base/go-publisher-deployment.yaml
```


## Documentación adicional

- **Swagger UI:** http://127.0.0.1:8000/docs
- **Métricas Prometheus:** http://127.0.0.1:8000/metrics
- **Endpoints principales:**
  - `POST /api/briefs` — crear brief de campaña
  - `POST /api/briefs/upload-asset` — subir foto del usuario (multipart)
  - `POST /api/runs/sync` — ejecutar pipeline sincrónicamente (rechaza `content_format=reel` con 422)
  - `POST /api/runs/async` — encolar ejecución (requiere Redis + worker; único camino para `content_format=reel`, cola dedicada `video_render`)
  - `GET /api/runs/{run_id}` — consultar estado
  - `GET /api/runs` — historial de ejecuciones
  - `GET /api/image/archetypes` — arquetipos para override manual
  - `GET /api/image/providers` — proveedores de imagen disponibles
  - `POST /api/campaigns` — crear campaña programada (cron)
  - `POST /api/campaigns/{id}/fire` — disparar campaña de inmediato (prueba de fuego)
- **Estado del proyecto (canónico):** [`estado-actual.txt`](estado-actual.txt)
- **Prueba de Fuego del Scheduler:** [`infra/prueba-de-fuego-scheduler.md`](infra/prueba-de-fuego-scheduler.md)
- **Arranque del stack completo (7 terminales):** [`infra/arranque-stack.md`](infra/arranque-stack.md)
