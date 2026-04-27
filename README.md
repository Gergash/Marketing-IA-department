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
| Backend API | FastAPI (Python) |
| Microservicios | Go |
| Base de datos | PostgreSQL + Redis |
| Migraciones | Alembic |
| Cola de tareas | Celery |
| Frontend | React + Vite |
| Contenido visual | Canva API / Stable Diffusion |
| Video | Shotstack |
| Contenedores | Docker |

## Estado del roadmap

- **Paso 1** ✅ Happy path local: API + frontend sin fricciones (CORS + proxy Vite)
- **Paso 2** ✅ PostgreSQL + Alembic: Docker Compose con healthchecks, migraciones versionadas
- **Paso 3** ✅ APIs reales: LLMs (Anthropic/OpenAI), imagen (DALL-E 3/Canva), social (LinkedIn/Upload-Post)
- **Paso 4** 🔲 Seguridad: Auth real, secrets, human-in-the-loop
- **Paso 5** 🔄 LangGraph: bucle **Copywriter ↔ QA** con trazabilidad (`copy_qa_trace`); resto del pipeline lineal — ver [`agents/PIPELINE.md`](agents/PIPELINE.md)
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

## Paso 1 — Happy path local (SQLite, sin Docker)

Desde la **raíz del repositorio**. No requiere Docker: la API usa SQLite por defecto.

**Terminal 1 — API**

```bash
python -m pip install -r requirements.txt
uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000
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

`DATABASE_URL` en `.env` ya viene configurada para Postgres local:

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/marketing_mvp
```

### Aplicar migraciones

```bash
python -m pip install -r requirements.txt   # incluye alembic
alembic upgrade head
```

Esto crea todas las tablas (`briefs`, `agent_runs`, `generated_assets`, `publications`, `campaign_schedules`).

### Iniciar la API contra Postgres

```bash
uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000
```

Con `DATABASE_URL` apuntando a Postgres, la API **no ejecuta** `create_all` — Alembic es la única fuente de verdad para el esquema.

### Flujo de trabajo con Alembic

| Acción | Comando |
|---|---|
| Aplicar todas las migraciones | `alembic upgrade head` |
| Ver migración actual | `alembic current` |
| Ver historial | `alembic history` |
| Revertir última migración | `alembic downgrade -1` |
| Generar nueva migración (auto) | `alembic revision --autogenerate -m "descripcion"` |

> **Importante:** después de modificar modelos en `gateway/app/models/entities.py`, genera siempre una nueva migración con `--autogenerate` y revisa el archivo generado antes de hacer `upgrade head`.

### Stack completo (Postgres + Redis + Worker + Frontend)

```bash
# 1. Infraestructura
docker compose -f infra/docker-compose.yml up -d

# 2. Migraciones
alembic upgrade head

# 3. API
uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000

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

Si `SOCIAL_PROVIDER=mock` (por defecto), la publicación genera una URL falsa sin llamadas externas.

---

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
