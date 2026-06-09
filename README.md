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
| Contenido visual | Canva API / Stable Diffusion |
| Video | Shotstack |
| Contenedores | Docker |

## Estado del roadmap

- **Paso 1** Happy path local: API + frontend sin fricciones (CORS + proxy Vite)
- **Paso 2** PostgreSQL + Alembic: Docker Compose con healthchecks, migraciones versionadas
- **Paso 3** APIs reales: LLMs (Anthropic/OpenAI), imagen (DALL-E 3/Canva), social (LinkedIn/Upload-Post)
- **Paso 4** Seguridad: Auth real, secrets, human-in-the-loop
- **Paso 5** LangGraph: bucle **Copywriter ↔ QA** con trazabilidad (`copy_qa_trace`); resto del pipeline lineal — ver [`agents/PIPELINE.md`](agents/PIPELINE.md)
- **Paso 6** 🔲 Go/infra: microservicios MCP, contenedores, Kubernetes

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

El proyecto está pensado para **Python 3.10** (misma línea que muchos entornos **Stable Diffusion / Automatic1111**). Hay un archivo `.python-version` para **pyenv**. Las imágenes Docker usan `python:3.10-slim`.

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
```

## Stable Diffusion (Realistic Vision u otro checkpoint)

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

### Stack completo (Postgres + Redis + Worker + Frontend)

```bash
# 1. Infraestructura
docker compose -f infra/docker-compose.yml up -d

# 2. Migraciones
python -m alembic upgrade head

# 3. API
python -m uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000

# 4. Worker Celery (otro terminal)
python -m celery -A workers.celery_app.celery_app worker -l info

# 5. Frontend (otro terminal)
cd frontend && npm run dev
```

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

### 3B — Imagen (diseño de posts)

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

**LinkedIn** (token de usuario con scope `w_member_social`):

```env
SOCIAL_PROVIDER=linkedin
LINKEDIN_ACCESS_TOKEN=...
# LINKEDIN_PERSON_URN=urn:li:person:xxx  # opcional; se obtiene automáticamente
```

**Upload-Post** (API unificada — LinkedIn, Instagram, Facebook, X, TikTok):

```env
SOCIAL_PROVIDER=uploadpost
UPLOADPOST_API_KEY=...
```

**Meta / Instagram Business** (publicación en feed o **historia** con Graph API; imagen en URL HTTPS pública):

```env
SOCIAL_PROVIDER=meta
META_PAGE_ACCESS_TOKEN=...
INSTAGRAM_BUSINESS_ACCOUNT_ID=...
# Opcional: META_APP_ID, META_APP_SECRET, GRAPH_API_VERSION=v21.0
```

- Comprueba credenciales sin exponer secretos: `GET /api/social/publish-status`.
- Al crear un run (`POST /api/runs/sync` o `/async`), envía `content_format`: `"feed"` o `"story"`. **Historias** vía API oficial requieren `SOCIAL_PROVIDER=meta` e Instagram profesional. LinkedIn hoy publica solo post de texto (historia no soportada en API UGC usada aquí).
- Las **historias** de Instagram suelen pedir imagen **9:16** y URL **HTTPS** accesible públicamente (Meta descarga la imagen desde tu servidor o CDN).

Si `SOCIAL_PROVIDER=mock` (por defecto), la publicación genera una URL falsa sin llamadas externas.

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
  - `POST /api/runs/sync` — ejecutar pipeline sincrónicamente
  - `POST /api/runs/async` — encolar ejecución (requiere Redis + worker)
  - `GET /api/runs/{run_id}` — consultar estado
  - `GET /api/runs` — historial de ejecuciones
  - `POST /api/campaigns` — crear campaña programada (cron)
  - `POST /api/campaigns/{id}/fire` — disparar campaña de inmediato (prueba de fuego)
- **Prueba de Fuego del Scheduler:** [`infra/prueba-de-fuego-scheduler.md`](infra/prueba-de-fuego-scheduler.md)
