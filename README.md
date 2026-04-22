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

## Quick start

1. Copia `.env.example` a `.env` y completa credenciales.
2. Levanta dependencias:
   - `docker compose -f infra/docker-compose.yml up -d`
3. Inicia API:
   - `uvicorn gateway.app.main:app --reload --port 8000`
4. Inicia worker:
   - `celery -A workers.celery_app.celery_app worker -l info`
5. Inicia frontend:
   - `cd frontend && npm install && npm run dev`
