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
| Modelos IA | Ollama (Llama 3, Mistral, Mixtral) |
| Backend API | FastAPI (Python) |
| Microservicios | Go |
| Base de datos | PostgreSQL + Redis + Qdrant |
| Cola de tareas | Celery / Temporal |
| Frontend | React + Tailwind CSS |
| Contenido visual | Stable Diffusion (AUTOMATIC1111 / ComfyUI) |
| Video | FFmpeg + MoviePy |
| Voz | Coqui TTS |
| Contenedores | Docker |
| Autenticación | Keycloak |
| Analítica | Metabase |

## Estado

MVP implementado por fases con base lista para escalar:

- Fase 0: estructura monorepo + contratos base
- Fase 1: pipeline sincronico end-to-end
- Fase 2: cola Redis + workers Celery + jobs asincornos
- Fase 3: primer microservicio en Go para publicacion social
- Fase 4: observabilidad, calidad de contenido, RBAC, scheduler

## Estructura

- `frontend/`: dashboard React para briefing, vista previa, publicacion e historial
- `gateway/`: API Gateway en FastAPI (sincronico + asincronico)
- `agents/`: agentes Python (estratega, copywriter, diseno, publicador)
- `workers/`: worker Celery para ejecucion en background
- `microservices/social-publisher-go/`: adaptador de publicacion en Go
- `infra/`: docker compose para Postgres/Redis

## Happy path local (API + frontend, sin fricción)

Desde la **raíz del repositorio** (donde está `gateway/` y `frontend/`). No hace falta Docker para esta prueba: la API usa SQLite por defecto.

**Terminal 1 — API**

```bash
python -m pip install -r requirements.txt
uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — dashboard**

```bash
cd frontend && npm install && npm run dev
```

Abre [http://localhost:5173](http://localhost:5173). El frontend en desarrollo usa **proxy** hacia la API (`/api` → `http://127.0.0.1:8000`). La API también expone **CORS** para esos orígenes por si llamas a `http://127.0.0.1:8000` desde el navegador.

Opcional: copia `.env.example` a `.env` y ajusta `CORS_ORIGINS` o `DATABASE_URL` si usas Postgres.

## Quick start (stack completo)

1. Copia `.env.example` a `.env` y completa credenciales.
2. Levanta dependencias:
   - `docker compose -f infra/docker-compose.yml up -d`
3. Inicia API:
   - `uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000`
4. Inicia worker:
   - `celery -A workers.celery_app.celery_app worker -l info`
5. Inicia frontend:
   - `cd frontend && npm install && npm run dev`
