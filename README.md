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
- **Paso 3** 🔲 APIs reales: LLMs, imagen, redes sociales
- **Paso 4** 🔲 Seguridad: Auth real, secrets, human-in-the-loop
- **Paso 5** 🔲 LangGraph: solo donde haya flujos cíclicos o recuperación compleja
- **Paso 6** 🔲 Go/infra: microservicios MCP, contenedores, Kubernetes

## Estructura

```
gateway/        API Gateway FastAPI (sync + async)
agents/         Agentes Python (estratega, copywriter, diseño, publicador)
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

`workers/celery_app.py` fuerza `worker_pool=solo` en Windows para evitar `PermissionError [WinError 5]` del pool `prefork`.

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
