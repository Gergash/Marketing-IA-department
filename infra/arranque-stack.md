# Arranque del stack completo — Marketing DEPA IA

Referencia de **comandos exactos** para levantar el MVP en Windows (Git Bash / PowerShell).  
Todos los servicios asumen que ya activaste el venv y estás en la raíz del repo salvo donde se indique otra ruta.

**Raíz del proyecto:** `~/Desktop/PowerUps/Marketing DEPA IA`

---

## Prerrequisitos (una sola vez)

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python -m alembic upgrade head
cd frontend && npm install && cd ..
```

Copia y configura `.env` desde `.env.example` (nunca commitear `.env`).

---

## Orden de arranque — 7–8 terminales

| # | Servicio | Cuándo | Puerto |
|---|----------|--------|--------|
| T1 | Docker (Postgres + Redis) | Siempre | 5433, 6379 |
| T2 | Ollama | Siempre (LLM) | 11434 |
| T3 | FastAPI (Uvicorn) | Siempre | 8000 |
| T4 | Celery worker (cola default) | Runs async imagen/story | — |
| T4b | Celery worker `video_render` | Solo Reels (`content_format=reel`) | — |
| T5 | Frontend Vite | Dashboard | 5173 |
| T6 | Go publisher | Al aprobar/publicar en IG / Reels | 8088 |
| T7 | ngrok | Al publicar en Meta (imagen o video) | túnel → 8000 |

---

### T1 — Infraestructura (Docker)

**PowerShell:**

```powershell
cd 'C:\Users\57317\Desktop\PowerUps\Marketing DEPA IA'
docker compose -f infra/docker-compose.yml up -d
```

**Git Bash:**

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA
docker compose -f infra/docker-compose.yml up -d
```

---

### T2 — Ollama (LLM local)

Ollama suele correr en segundo plano en Windows. Verifica que responde:

```bash
curl http://localhost:11434/api/tags
```

Debe listar `llama3.1:latest` (u otro modelo configurado en `.env` → `OLLAMA_MODEL=llama3.1`).

Si no está instalado el modelo:

```bash
ollama pull llama3.1
```

---

### T3 — API (FastAPI + APScheduler)

Desde la **raíz** del repo, venv activado:

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA
source .venv/Scripts/activate
python -m uvicorn gateway.app.main:app --reload --host 127.0.0.1 --port 8000
```

- Swagger: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/api/health  

---

### T4 — Celery worker (cola async)

Otra terminal, misma raíz y venv:

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA
source .venv/Scripts/activate
python -m celery -A workers.celery_app.celery_app worker -l info
```

Necesario para **Enviar async** desde el dashboard (formatos `feed` y `story`).

---

### T4b — Celery worker cola `video_render` (Reels)

Solo si vas a generar **`content_format=reel`**. Los renders de video tardan minutos y usan una cola dedicada (no compite con imágenes):

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA
source .venv/Scripts/activate
python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render
```

Requisitos en `.env`: `VIDEO_PROVIDER=shotstack`, `SHOTSTACK_API_KEY`, `VOICE_PROVIDER=elevenlabs`, `ELEVENLABS_API_KEY` (ver sección PASO 3D en `.env.example`).  
`/runs/sync` con `reel` responde **422** — usa siempre **Enviar async**.

---

### T5 — Frontend (React + Vite)

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA/frontend
npm run dev
```

Abre http://localhost:5173 (proxy `/api` → `:8000`).

---

### T6 — Go publisher (publicación Meta/Instagram)

Solo cuando vayas a **Aprobar** un run y publicar en Instagram:

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA/microservices/social-publisher-go
go run ./cmd/server
```

Log esperado: `social-publisher-go escuchando en :8088`

---

### T7 — ngrok (URL pública para Meta)

Meta exige HTTPS para descargar **imágenes y videos**. El túnel apunta al **API (:8000)**, no al frontend.

Ejecutable incluido en el repo:

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA/tests/ngrok-v3-stable-windows-amd64
./ngrok.exe http 8000
```

Copia la URL **https** (ej. `https://xxxx.ngrok-free.dev`) y actualiza en `.env`:

```env
PUBLIC_IMAGE_BASE_URL=https://xxxx.ngrok-free.dev
```

Reinicia **Uvicorn** (T3) tras cambiar `.env`.

---

## Flujo de prueba rápida (fal.ai + human-in-the-loop)

1. T1–T5 levantados (T4b solo para Reels; T6–T7 solo si publicas en IG).
2. `.env`: `IMAGE_PROVIDER=fal`, `FAL_API_KEY=...`, `LLM_PROVIDER=ollama`.
3. Dashboard → crear brief → formato **feed** o **story** → **Enviar async**.
4. Esperar `pending_approval` con imagen en Resultado.
5. T6 + T7 → un solo clic en **Aprobar**.

### Flujo Reels (Video-as-Code)

1. T1–T5 + **T4b** (`video_render`).
2. `.env`: además `VIDEO_PROVIDER=shotstack`, `VOICE_PROVIDER=elevenlabs` (+ API keys).
3. Dashboard → formato **reel** → **Enviar async** (no usar Sync).
4. Esperar `pending_approval` con preview `<video>` en Resultado.
5. T6 + T7 → **Aprobar** (Go publica con `media_type=REELS`).

---

## Mínimo por escenario

| Escenario | Terminales necesarias |
|-----------|------------------------|
| Solo generar contenido imagen (fal.ai) | T1, T2, T3, T4, T5 |
| Generar Reels (Shotstack + voz) | T1, T2, T3, T4, **T4b**, T5 |
| Publicar en Instagram (imagen o reel) | + T6, T7 |
| Prueba de fuego scheduler | T3 (+ seed script, sin Celery obligatorio) |

Runbook scheduler: [`prueba-de-fuego-scheduler.md`](prueba-de-fuego-scheduler.md)

---

## Checklist de salud

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/health/background   # Redis + Celery
curl -s http://localhost:11434/api/tags
curl -s http://127.0.0.1:8088/health                   # Go (si está levantado)
```
