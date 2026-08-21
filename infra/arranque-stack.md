# Arranque del stack completo — Marketing DEPA IA

Referencia de **comandos exactos** para levantar el MVP en Windows (Git Bash / PowerShell).  
Todos los servicios asumen que ya activaste el venv y estás en la raíz del repo salvo donde se indique otra ruta.

**Producción en la VPS (Hostinger + InsightFlow):** no uses esta guía. Ve a [`deploy/vps-hostinger.md`](deploy/vps-hostinger.md) y el estado del proceso en [`deploy/proceso-integracion-redes.md`](deploy/proceso-integracion-redes.md).

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
| T4 | Celery worker (cola `celery`) | Runs async de imagen (`feed` / `story` / `universal`) | — |
| T4b | Celery worker (cola `video_render`) | Reels y clips Drive (`reel` / `user_clip_reel`) | — |
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

### T4 — Celery worker (cola default `celery`)

Otra terminal, misma raíz y venv:

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA
source .venv/Scripts/activate
python -m celery -A workers.celery_app.celery_app worker -l info
```

Necesario para **Enviar Async** con formatos de imagen (`feed`, `story`, `universal`).

Al arrancar, el banner **`[tasks]`** debe listar al menos:

```
. workers.tasks.execute_pipeline_task
. workers.tasks.execute_video_pipeline_task
. workers.healthcheck_task
```

Si `[tasks]` aparece vacío, el worker descartará jobs (`unregistered task`). Causa habitual: proceso viejo sin reiniciar tras cambios en `workers/celery_app.py` (ese módulo importa `workers.tasks` al cargar).

---

### T4b — Celery worker cola `video_render` (Reels)

**Obligatorio** para `content_format=reel` o `user_clip_reel`. Los renders tardan minutos y van a una cola dedicada (no compiten con imágenes):

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA
source .venv/Scripts/activate
python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render
```

Comprueba el banner:

```
[queues]
  .> video_render
[tasks]
  . workers.tasks.execute_pipeline_task
  . workers.tasks.execute_video_pipeline_task
  . workers.healthcheck_task
```

**Notas:**

- `POST /runs/sync` con `reel` / `user_clip_reel` responde **422**. En el dashboard, aunque pulses Sync, el frontend **fuerza Async** y el run queda en `queued` hasta que T4b lo consuma.
- Sin T4b: el job queda en Redis en cola `video_render` y el historial no avanza de `queued`.
- Requisitos `.env` (Reel generado): `VIDEO_PROVIDER=shotstack`, `SHOTSTACK_API_KEY`, `SHOTSTACK_ENV=stage` (sandbox) o `v1`, `VOICE_PROVIDER=fal` (reusa `FAL_API_KEY`) o `elevenlabs` + key. Con `VOICE_PROVIDER=fal` / fondos fal.ai, Shotstack descarga directo de `fal.media` (no hace falta ngrok para el render). ngrok (`PUBLIC_IMAGE_BASE_URL`) sigue siendo obligatorio para **publicar en Meta** y para clips locales (`user_clip_reel` / overlays Pillow). Alternativa local: `VIDEO_PROVIDER=mock` / `VOICE_PROVIDER=mock`. Ver PASO 3D en `.env.example`.
- `user_clip_reel` además: `ffmpeg` en PATH, OAuth Google y `drive_folder_id` en el formulario.
- Timeout de video: `execute_video_pipeline_task` usa hasta ~20 min (`task_annotations` en `workers/celery_app.py`); el default de otras tareas sigue en 120s.
- Tras cambiar `.env` o código de video: **reinicia T4b** (Celery no recarga env/módulos solos).

**PowerShell (mismo comando):**

```powershell
cd 'C:\Users\57317\Desktop\PowerUps\Marketing DEPA IA'
.\.venv\Scripts\Activate.ps1
python -m celery -A workers.celery_app.celery_app worker -l info -Q video_render
```

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

### T7 — ngrok (URL pública para Meta + assets locales)

Meta (al publicar) y Shotstack (cuando el edit usa assets **locales**) necesitan HTTPS. El túnel apunta al **API (:8000)**, no al frontend.

- **Reel estándar con fal:** fondos/voz van a Shotstack como URLs `fal.media` → ngrok **no** es obligatorio solo para renderizar.
- **Siempre obligatorio:** publicar en Meta/Instagram, y `user_clip_reel` / overlays Pillow / wan-effects con clips en `localhost`.

Ejecutable incluido en el repo:

```bash
cd ~/Desktop/PowerUps/Marketing\ DEPA\ IA/tests/ngrok-v3-stable-windows-amd64
# Plan Free rota el dominio en cada arranque; preferible dominio reservado:
./ngrok.exe http --url=TU-DOMINIO.ngrok-free.dev 8000
# Sin dominio fijo:
# ./ngrok.exe http 8000
```

Copia la URL **https** y actualiza en `.env`:

```env
PUBLIC_IMAGE_BASE_URL=https://TU-DOMINIO.ngrok-free.dev
META_REDIRECT_URI=https://TU-DOMINIO.ngrok-free.dev/api/auth/callback/meta
```

En Meta Developers → Valid OAuth Redirect URIs: pegar la **URI completa** (path incluido), no solo el dominio. Reinicia **Uvicorn (T3)** y el **worker video_render (T4b)** tras cambiar `.env`.

---

## Flujo de prueba rápida (fal.ai / Venice + marca + HITL)

1. T1–T5 levantados (T4b solo para Reels; T6–T7 solo si publicas en IG).
2. `.env`: `IMAGE_PROVIDER=fal` (o `venice` + `VENICE_API_KEY`), `LLM_PROVIDER=ollama`, `OCR_PROVIDER=paddle` si usas PDFs escaneados.
3. Dashboard → **Manual de marca (PDF)** → subir brand book (aparecen paleta + logos si el scan encuentra).
4. Crear brief → elegir **Red social** y **Formato** (feed / story / universal) → **Cuenta destino** → **Enviar async**.
5. Esperar `pending_approval` con pieza (con marca: arquetipo campaña + logo).
6. T6 + T7 → **Aprobar** (o **Solicitar cambios** con notas).

### Flujo Reels (Video-as-Code)

1. T1–T5 + **T4b** (`-Q video_render`). **T7** obligatorio para Meta o `user_clip_reel`.
2. `.env`: `VIDEO_PROVIDER=shotstack`, `SHOTSTACK_*`, `VOICE_PROVIDER=fal`; opcional `VIDEO_SCENE_PROVIDER=venice`.
3. Dashboard → **Reel** (o **Video con mis clips**) → **Enviar Async**.
4. Historial: `queued` → `running` → `pending_approval` con preview `<video>`.
5. T6 (+ T7) → **Aprobar**.

### Dependencias OCR / marca (una vez)

```bash
pip install pypdf pymupdf paddlepaddle paddleocr
# OCR_PROVIDER=paddle en .env; reiniciar Uvicorn tras instalar
```

Si el worker loguea `unregistered task of type 'workers.tasks.execute_video_pipeline_task'`: reinicia T4 y T4b, y lanza un run **nuevo**.

Si Shotstack responde `400`, el log de T4b incluye `body=...` con el detalle de validación.

---

## Mínimo por escenario

| Escenario | Terminales necesarias |
|-----------|------------------------|
| Solo generar imagen (fal/Venice) + marca PDF | T1, T2, T3, T4, T5 |
| Generar Reels (Shotstack + voz; escenas still/venice) | T1, T2, T3, T4, **T4b**, T5 |
| Reel con clips de Drive | T1, T2, T3, T4, **T4b**, T5, **T7** (+ ffmpeg + Google OAuth) |
| Publicar en Instagram (imagen o reel) | + T6, T7 (ngrok + OAuth scopes IG) |
| Multi-cuenta (Cliente A / Cliente B) | T3 + Integraciones + selector **Cuenta destino**; migración `0007` |
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
