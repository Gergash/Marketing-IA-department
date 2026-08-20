# Marketing DEPA IA — Fuente completa para NotebookLM

**Proyecto:** Marketing DEPA IA (PowerUps)  
**Tipo:** MVP de automatización de marketing con agentes de IA  
**Actualizado:** 2026-08-11  
**Idioma:** español  

Este documento es **autocontenido**: súbelo como única fuente (o como fuente principal) a NotebookLM. No depende de enlaces internos del repositorio.

---

## 1. En una frase

Marketing DEPA IA genera piezas de redes (feed, story, Reel o formato universal multi-red) a partir de un brief y un manual de marca PDF, pasa por aprobación humana y publica en Instagram (Meta) o LinkedIn.

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
| Hilo de pensamiento (`thought_stream`) | Eventos en vivo de cada agente por `trace_id`; en modo interactivo el pipeline se detiene en checkpoints y espera `continue` / `adjust` / `cancel` |

Doctrina de marketing inbound: pirámide **Entretener → Información → Conexión**; el contenido debe apuntar a la comunidad del brief (`publico_objetivo`), no a audiencia genérica.

---

## 6. Formatos de contenido

| Formato | Qué produce | Restricción |
|--------|-------------|-------------|
| `feed` | Imagen editorial, dimensión según la red | Sync o async |
| `story` | Imagen 9:16 con tipografía centrada | Sync o async; no existe en LinkedIn ni X |
| `universal` | Imagen **1080×1080** idéntica en todas las redes | Sync o async; para publicar el mismo post en varias redes |
| `reel` | Video 9:16 generado (script → escenas → voz → Shotstack) | Solo async + worker `video_render` |
| `user_clip_reel` | Video desde clips del usuario en Drive | Solo async; requiere `drive_folder_id` y `ffmpeg` |

### Formatos por red social

El catálogo vive en `image_specs.py` y se sirve por `GET /api/image/formats`; el dashboard solo ofrece los formatos válidos de la red elegida.

| Red | Formatos | Dimensión de feed |
|-----|----------|-------------------|
| Instagram / Facebook | feed, story, reel, user_clip_reel, universal | 1080×1350 |
| LinkedIn | feed, universal | 1200×627 |
| TikTok | story, reel, user_clip_reel, universal | vertical 1080×1920 |
| X (Twitter) | feed, reel, universal | 1200×675 |

**Por qué 1:1 es el universal:** es el único encuadre que ninguna red recorta de forma agresiva. Internamente `universal` se comporta como `feed` (mismo layout, misma ruta de publicación), así que no toca el pipeline de video.

**TikTok y X solo generan la pieza.** No hay publicación automática: al aprobar, el sistema responde "publicación no soportada" en lugar de mandar la pieza a un publisher que no soporta esas plataformas. Descargar y publicar a mano es el camino actual.

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
- Modos de generación (`video_gen_mode`): `full` = Venice genera un clip completo; `scenes` = Venice anima cada toma y Shotstack las une; `still` = stills + Ken Burns sin video AI.
- Modelos Venice: Seedance 2.5 / 2.0, Kling O3, MiniMax H3 (aliases resueltos en `venice_video_models.py`).
- Voz: fal Kokoro Spanish (típico en dev), ElevenLabs u OpenAI TTS.
- URLs públicas: ngrok / `PUBLIC_IMAGE_BASE_URL` obligatorio para Meta y assets locales; fondos fal pueden ir a Shotstack como URLs `fal.media`.

---

## 9. Publicación social y HITL

### Redes
- Instagram / Meta (feed, stories, Reels) vía Graph API y sidecar Go.
- LinkedIn nativo **solo desde Python**: API versionada `/rest/images` + `/rest/posts` con header `LinkedIn-Version`. Solo imagen y solo perfil personal; el token dura ~60 días sin refresh automático (la UI avisa a ≤7 días).
- TikTok y X: **sin publicación automática** — se genera la pieza y se publica a mano.
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

### Contraste de texto (resuelto)
`text_contrast.py` muestrea la luminancia de la región donde va el texto (`region_luminance`, `text_safe_box`) y elige color y viñeta en consecuencia (`pick_text_colors`). Ya no depende solo de sombras fijas del arquetipo.

---

## 10. API REST (resumen)

Prefijo típico: `/api`.

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/health`, `/health/background` | Salud API / Redis+Celery |
| GET | `/image/providers`, `/image/archetypes` | Generadores y layouts |
| GET | `/image/formats` | Formatos válidos por red + dimensiones |
| GET | `/video/options` | Modos y modelos de video Venice |
| GET/POST | `/thoughts/{trace_id}`, `/thoughts/{trace_id}/reply` | Hilo de pensamiento y checkpoints |
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
- **Red social** y **Formato de publicación**: dos selects acoplados alimentados por `/image/formats`; al cambiar de red se corrige el formato si dejó de ser válido.
- Video (solo en `reel`): modo de generación y modelo Venice.
- Selector de generador de imagen (fal / Venice / SD según keys).
- Upload de manual de marca con preview de paleta y logos.
- Upload de foto + toggle alterar con IA.
- Selector de cuenta destino, enlace opcional, CTA en imagen opcional.
- Modo interactivo + hilo de pensamiento en vivo de los agentes.
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

- Suite pytest de **271 tests** (2026-08-11).
- Cobertura fuerte: pipeline, layouts, formatos por red, video, clips, revise, multi-cuenta, marca, Venice, captions, hilo de pensamiento, LinkedIn nativo.
- Migraciones Alembic relevantes: `0005` video_url, `0006` revise fields, `0007` multi-cuenta OAuth.
- 3 fallos conocidos y preexistentes en `test_venice.py` y `test_video_timeline_clips.py` (estructura del edit Shotstack).

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
| Hilo de pensamiento + modo interactivo | Hecho |
| Contraste tipográfico adaptativo | Hecho |
| Formatos por red + universal 1:1 | Hecho (diseño) |
| Kubernetes / Skaffold | Escrito, sin clúster real |
| Canva / Figma MCP | Pendiente |
| Publicación nativa TikTok / X | Pendiente (TikTok requiere auditoría de app) |
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
7. TikTok y X: la pieza se genera pero hay que publicarla a mano.
8. El formato `universal` cubre solo imagen; los reels siguen siendo 9:16 por red.
9. LinkedIn: sin refresh automático del token (~60 días) y sin páginas de empresa.

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
| Formato universal | Pieza 1080×1080 que encaja en todas las redes sin recortes |
| Hilo de pensamiento | Stream de eventos de los agentes por `trace_id`, con checkpoints interactivos |

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
- ¿Qué formato uso si voy a publicar el mismo post en varias redes?
- ¿Por qué LinkedIn no ofrece historias ni reels en el dashboard?
- ¿Qué pasa al aprobar una pieza de TikTok o X?

---

## 18. Resumen ejecutivo

Marketing DEPA IA es un MVP local completo para generar copy e identidades visuales con agentes, respetar un brand book (OCR + paleta + logos), producir Reels o clips, elegir el formato correcto de cada red (o uno universal para publicar en varias a la vez) y publicar con control humano en Meta o LinkedIn. Lo más maduro es generación + marca + formatos + HITL + multi-cuenta. Lo más débil hoy es la **revisión de piezas** (notas que no mandan del todo en copy/overlay) y la **publicación fuera de Meta/LinkedIn**: TikTok y X se diseñan pero se publican a mano.
