# Marketing DEPA IA — Fuente completa para NotebookLM

**Proyecto:** Marketing DEPA IA (PowerUps)  
**Tipo:** MVP de automatización de marketing con agentes de IA  
**Actualizado:** 2026-08-04  
**Idioma:** español  

Este documento es **autocontenido**: súbelo como única fuente (o como fuente principal) a NotebookLM. No depende de enlaces internos del repositorio.

---

## 1. En una frase

Marketing DEPA IA genera piezas de redes (feed, story, Reel) a partir de un brief y un manual de marca PDF, pasa por aprobación humana y publica en Instagram (Meta) o LinkedIn mediante un sidecar en Go.

---

## 2. Flujo de valor (happy path)

1. El usuario describe el producto o evento (brief) y opcionalmente sube el PDF de marca.
2. Los agentes producen estrategia, copy con control de calidad, y diseño (imagen o video).
3. El run queda en `pending_approval` (human-in-the-loop).
4. Un humano aprueba, rechaza o solicita cambios.
5. Al aprobar, se publica en la cuenta social elegida.

Cadena lógica:

```
brief (+ manual de marca)
  → estratega
  → copywriter ↔ QA (LangGraph)
  → diseñador | video designer | clip reel designer
  → aprobación humana
  → publicación Meta o LinkedIn
```

---

## 3. Stack tecnológico

| Capa | Tecnología | Puerto / nota |
|------|------------|---------------|
| Frontend | React + Vite | 5173; proxy `/api` → 8000 |
| API | FastAPI (Python 3.10) + Alembic | 8000 |
| Base de datos | PostgreSQL | host 5433 → contenedor 5432 |
| Cola | Redis + Celery | 6379; colas `celery` y `video_render` |
| Publicación | Go (`social-publisher-go`) | 8088 |
| LLM | Ollama / Anthropic / OpenAI | 11434 si Ollama |
| Imagen | fal.ai (Flux), Venice.ai, Stable Diffusion, DALL·E | configurable |
| Video | Shotstack + TTS (fal Kokoro / ElevenLabs / OpenAI) | Reels async |
| Marca / OCR | pypdf + PaddleOCR + PyMuPDF + escaneo visual | PDF ≤ 20 MB |
| Scheduler | APScheduler | campañas programadas |
| Observabilidad | Prometheus opcional | `/metrics` si está activo |

---

## 4. Arquitectura de componentes

```
Dashboard React (:5173) + burbuja Asesor creativo
        ↓
Gateway FastAPI (:8000)  ←→  PostgreSQL + Redis
        ↓
Workers Celery (imagen) + worker video_render (Reels)
        ↓
Agentes Python (agents/marketing_agents/)
        ↓
Go publisher (:8088) → Meta Graph API / LinkedIn UGC
```

Infra local típica: Docker Compose solo para Postgres y Redis; el resto corre en terminales (Uvicorn, Celery ×2, Vite, Go, ngrok).

---

## 5. Agentes y responsabilidades

| Agente / módulo | Rol |
|-----------------|-----|
| ContentStrategistAgent | Tipo de post, hook, mensaje base, hashtags; doctrina inbound + marca |
| CopywriterAgent | Caption, headline/subline de overlay, CTA, hashtags |
| ContentQualityGuard + LangGraph | Bucle copy ↔ QA (hasta ~3 intentos) con trazabilidad |
| DesignerAgent | Arquetipo visual + generación de imagen + overlay Pillow + logo |
| VideoScriptAgent | Guion de Reel 3–5 escenas (~15–30 s) |
| VideoDesignerAgent | Stills, voz, timeline, render Shotstack; escenas still o Venice i2v |
| ClipReelDesigner | Clips de Google Drive → Whisper → selección → Shotstack |
| PublisherAgent | Publicación (imagen); video vía Go al aprobar |
| CreativeAdvisorAgent | Chat de asesoría (fuera del pipeline) |

Doctrina de marketing inbound: pirámide **Entretener → Información → Conexión**; el contenido debe apuntar a la comunidad del brief (`publico_objetivo`), no a audiencia genérica.

---

## 6. Formatos de contenido

| Formato | Qué produce | Restricción |
|--------|-------------|-------------|
| `feed` | Imagen editorial (p. ej. Instagram 1080×1350) | Sync o async |
| `story` | Imagen 9:16 con tipografía centrada | Sync o async |
| `reel` | Video 9:16 generado (script → escenas → voz → Shotstack) | Solo async + worker `video_render` |
| `user_clip_reel` | Video desde clips del usuario en Drive | Solo async; requiere `drive_folder_id` y `ffmpeg` |

---

## 7. Manual de marca (identidad visual)

### Entrada
- Endpoint: subir PDF del brand book.
- Límite: 20 MB.

### Procesamiento
1. Extracción de texto con pypdf.
2. Si hay poco texto y OCR activo: PaddleOCR (PDF rasterizado con PyMuPDF).
3. Escaneo visual (`brand_scan`): paleta de colores dominante + logos embebidos o recortes de cabecera.
4. Persistencia: PDF, texto, JSON visual, `active.json` por tenant.

### Uso en diseño
- Colores, tipografías y logos alimentan el brief.
- Con señales de marca, el diseño prioriza el arquetipo **`brand_campaign_piece`**: foto full-bleed, logo arriba-centro, headline expresivo, CTA, eslogan opcional.
- Tipografías premium empaquetadas (OFL): Great Vibes, Playfair Display, Montserrat.

### Arquetipos visuales (IDs estables)

| ID | Cuándo |
|----|--------|
| `brand_campaign_piece` | Manual de marca activo |
| `typographic_poster` | Promocional / ventas |
| `minimal_conceptual` | Informativo |
| `editorial_infographic` | Educativo / branding sin manual |
| `cinematic_hero` | Storytelling / entretenimiento |

---

## 8. Proveedores de imagen y video

### Imagen
- **fal.ai** — principal (Flux); también img2img si el usuario sube foto y activa “Alterar con IA”.
- **Venice.ai** — alternativa; base API `https://api.venice.ai/api/v1`.
- **Stable Diffusion** — Automatic1111/Forge local.
- **OpenAI DALL·E** — si hay key.
- **mock** — solo desarrollo/tests.
- Fallos de fal/Venice/SD: error explícito (no placeholder silencioso disfrazado de éxito).

### Video
- Render: Shotstack (`stage` sandbox o `v1` producción).
- Escenas de Reel: `still` (Ken Burns) o `venice` (image-to-video por escena).
- Voz: fal Kokoro Spanish (típico en dev), ElevenLabs u OpenAI TTS.
- URLs públicas: ngrok / `PUBLIC_IMAGE_BASE_URL` obligatorio para Meta y assets locales; fondos fal pueden ir a Shotstack como URLs `fal.media`.

---

## 9. Publicación social y HITL

### Redes
- Instagram / Meta (feed, stories, Reels) vía Graph API y Go.
- LinkedIn nativo (imagen + UGC).
- Multi-cuenta: N cuentas por proveedor; el run elige `social_account_id` (Cuenta destino).

### Human-in-the-loop
- Estados relevantes: `queued` → `running` → `pending_approval` → aprobado / rechazado / regenerado.
- Acciones: Aprobar, Rechazar, Solicitar cambios (`revise`).
- Una revisión **nunca publica sola**: vuelve a `pending_approval`.

### Limitación actual de “Solicitar cambios” (importante)
La UI y el endpoint están conectados, pero las notas de revisión:
- se inyectan sobre todo en el **prompt** del generador de imagen / guion de video;
- **no** se pasan al copywriter de forma específica;
- **no** ajustan automáticamente tipografía, color ni contraste del overlay Pillow;
- con foto de usuario sin “Alterar con IA”, el fondo puede no cambiar.

Por eso a veces el usuario siente que “los cambios no se aplican”.

### Limitación de contraste de texto
Hoy la legibilidad se apoya en viñetas oscuras y sombras, no en muestreo de luminancia del fondo. El color del texto viene del arquetipo o del manual de marca; no se adapta automáticamente a cada foto.

---

## 10. API REST (resumen)

Prefijo típico: `/api`.

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/health`, `/health/background` | Salud API / Redis+Celery |
| GET | `/image/providers`, `/image/archetypes` | Generadores y layouts |
| POST | `/briefs/upload-asset` | Foto del usuario |
| POST | `/briefs/upload-brand-manual` | PDF de marca |
| GET/DELETE | `/briefs/brand-manual` | Manual activo |
| POST | `/advisor/chat` | Asesor creativo |
| POST/GET | `/briefs` | Crear / listar briefs |
| POST | `/runs/sync`, `/runs/async` | Ejecutar pipeline |
| POST | `/runs/{id}/approve\|reject\|revise` | HITL |
| GET | `/runs`, `/runs/{id}` | Historial / estado |
| POST/GET | `/campaigns`, POST `.../fire` | Scheduler |
| GET | `/auth/login/{provider}`, callbacks, `/auth/accounts` | OAuth multi-cuenta |

Swagger local: `http://127.0.0.1:8000/docs`.

---

## 11. Frontend (dashboard)

- Campo de brief: “Descripción del producto o evento”.
- Formato: feed / story / reel / video con clips Drive.
- Selector de generador de imagen (fal / Venice / SD según keys).
- Upload de manual de marca con preview de paleta y logos.
- Upload de foto + toggle alterar con IA.
- Selector de cuenta destino, enlace opcional, CTA en imagen opcional.
- Sync / Async, historial, Integraciones OAuth, burbuja del Asesor.

---

## 12. Cómo levantar el stack (Windows / local)

Orden típico (7–8 terminales):

1. Docker: Postgres + Redis (`infra/docker-compose.yml`).
2. Ollama (si el LLM es local).
3. Uvicorn gateway `:8000`.
4. Celery worker cola default (feed/story).
5. Celery worker `-Q video_render` (obligatorio para Reels).
6. Frontend Vite `:5173`.
7. Go publisher `:8088` (al publicar).
8. ngrok → `:8000` y actualizar `PUBLIC_IMAGE_BASE_URL` (Meta / assets locales).

Variables mínimas conceptuales:
- `IMAGE_PROVIDER`, keys fal/Venice
- `OCR_PROVIDER=paddle` para PDFs escaneados
- `LLM_PROVIDER` + modelo
- `DATABASE_URL` en puerto 5433
- `REDIS_URL`, `GO_PUBLISHER_URL`
- `VIDEO_PROVIDER=shotstack`, `VOICE_PROVIDER`
- `PUBLIC_IMAGE_BASE_URL` HTTPS

Dependencias de sistema: Python 3.10, Node, Docker, Go (publicar), ffmpeg (clips Drive), opcionalmente PaddleOCR.

---

## 13. Tests y calidad

- Suite pytest del orden de **~214 tests** (documentado 2026-08-03).
- Cobertura fuerte: pipeline, layouts, video, clips, revise, multi-cuenta, marca, Venice, captions.
- Migraciones Alembic relevantes: `0005` video_url, `0006` revise fields, `0007` multi-cuenta OAuth.

---

## 14. Roadmap vs realidad

| Área | Estado |
|------|--------|
| Happy path, Postgres, APIs, HITL, LangGraph Copy/QA | Hecho |
| Diseño editorial + foto usuario + LinkedIn nativo | Hecho |
| Reels + clips Drive | Hecho |
| Revise API + multi-cuenta | Hecho (revise superficial en diseño) |
| Manual de marca OCR + scan + campaña | Hecho |
| Venice.ai imagen / escenas | Hecho |
| Asesor creativo | Hecho |
| Sidecar Go | Hecho |
| Kubernetes / Skaffold | Escrito, sin clúster real |
| Canva / Figma MCP | Pendiente |
| TikTok | Fase 2 (requiere auditoría de app) |
| Contraste tipográfico adaptativo | Pendiente |
| Revise que mueva copy + overlay de verdad | Pendiente |
| Error de LLM visible en UI | Pendiente |

---

## 15. Deuda y riesgos operativos

1. Stub silencioso del LLM si Ollama/API falla → copy genérico sin aviso claro en UI.
2. Meta/Instagram: scopes OAuth, tokens de Página, ngrok con dominio estable.
3. Reels: sin worker `video_render` el job queda encolado para siempre.
4. Canva OAuth y plantillas MCP no implementados.
5. CI/CD K8s no estrenado en GKE real.
6. Video v2 pendiente: música de fondo, captions por palabra en clips de usuario.

---

## 16. Glosario rápido

| Término | Significado |
|---------|-------------|
| Brief | Entrada de campaña (tema, público, red, objetivo, tono) |
| HITL | Human-in-the-loop: aprobación humana antes de publicar |
| Brand campaign piece | Layout canónico cuando hay manual de marca |
| video_render | Cola Celery dedicada a renders de video |
| Design-as-Code | Foto del usuario como capa base + overlay programático |
| Inbound | Marco Attract→Convert→Close→Delight + pirámide de fines en redes |

---

## 17. Preguntas útiles para hacerle a NotebookLM

- ¿Cuál es el flujo completo desde el brief hasta la publicación?
- ¿Qué hace el manual de marca en el diseño?
- ¿Por qué un Reel no puede ir por `/runs/sync`?
- ¿Qué terminales hay que levantar para publicar en Instagram?
- ¿Qué limita hoy “Solicitar cambios”?
- ¿Qué arquetipo se usa con brand book?
- ¿Qué proveedores de imagen existen y cuál es el principal?
- ¿Qué es multi-cuenta y cómo se elige la cuenta destino?

---

## 18. Resumen ejecutivo

Marketing DEPA IA es un MVP local completo para generar copy e identidades visuales con agentes, respetar un brand book (OCR + paleta + logos), producir Reels o clips, y publicar con control humano en Meta o LinkedIn. Lo más maduro es generación + marca + HITL + multi-cuenta. Lo más débil hoy para la experiencia creativa es la **revisión de piezas** (notas que no mandan del todo en copy/overlay) y el **contraste automático del texto** sobre fondos variables.
