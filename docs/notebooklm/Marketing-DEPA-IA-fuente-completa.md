# Marketing DEPA IA — Fuente completa para NotebookLM

**Proyecto:** Marketing DEPA IA (PowerUps)  
**Tipo:** MVP de automatización de marketing con agentes de IA  
**Actualizado:** 2026-09-10  
**Nota 2026-09-17:** esta fuente **no** cubre Auth0-only ni el panel `/admin`. Usar `estado-actual.txt` + `docs/estado-saas-auth0-2026-09-17.md` como complemento hasta reescribir esta página.  
**Idioma:** español  

Este documento es **autocontenido**: súbelo como única fuente (o como fuente principal) a NotebookLM. No depende de enlaces internos del repositorio.

---

## 1. En una frase

Marketing DEPA IA genera piezas de redes (feed, story, Reel, clips propios o formato universal multi-red) a partir de un brief y un manual de marca PDF, pasa por aprobación humana (incluye HITL de tomas en clips Drive) y publica en Instagram/Meta, LinkedIn o X.

---

## 2. Flujo de valor (happy path)

1. El usuario describe el producto o evento (brief) y opcionalmente sube el PDF de marca; conecta redes (y Google Drive si usa clips).
2. Los agentes producen estrategia, copy con control de calidad, y diseño (imagen o video).
3. En clips Drive: el run llega a `pending_takes` (aceptar/reordenar tomas) y luego se renderiza el MP4.
4. El run queda en `pending_approval` (human-in-the-loop del resultado).
5. Un humano aprueba, rechaza o solicita cambios.
6. Al aprobar, se publica en la cuenta social elegida.

Cadena lógica:

```
brief (+ manual de marca)
  → estratega
  → copywriter ↔ QA (LangGraph)
  → diseñador | video designer | clip reel (cloud + VideoProducer)
  → [pending_takes si clips] → pending_approval
  → publicación Meta / LinkedIn / X
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
| ClipReelDesigner + VideoProducerAgent | Drive cloud: audio-only → N tomas → pending_takes → shorts → Shotstack |
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
| `user_clip_reel` | Video desde clips Drive (sin bajar máster; HITL de tomas) | Solo async; `drive_folder_id`, `editing_goal`, `take_count`, `ffmpeg`, OAuth Google |

### Formatos por red social

El catálogo vive en `image_specs.py` y se sirve por `GET /api/image/formats`; el dashboard solo ofrece los formatos válidos de la red elegida.

| Red | Formatos | Dimensión de feed |
|-----|----------|-------------------|
| Instagram / Facebook | feed, story, reel, user_clip_reel, universal | 1080×1350 |
| LinkedIn | feed, universal | 1200×627 |
| TikTok | story, reel, user_clip_reel, universal | vertical 1080×1920 |
| X (Twitter) | feed, reel, universal | 1200×675 |

**Por qué 1:1 es el universal:** es el único encuadre que ninguna red recorta de forma agresiva. Internamente `universal` se comporta como `feed` (mismo layout, misma ruta de publicación), así que no toca el pipeline de video.

**TikTok** solo genera la pieza (publish tras App Review). **X** ya publica nativo (tweet + imagen en feed).

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
- **Venice.ai** — recomendado para evaluación y **edición de foto real** (`gpt-image-2` + `gpt-image-2-edit` vía `/image/edit`). Tipografía = Pillow, no la IA. Guía: `docs/foto-real-venice-edit.md`.
- **fal.ai** — generación desde cero (Flux); img2img opcional (puede deformar textos ya en la foto).
- **Stable Diffusion** — Automatic1111/Forge local.
- **OpenAI DALL·E** — si hay key.
- **mock** — solo desarrollo/tests.
- Fallos de fal/Venice/SD: error explícito (no placeholder silencioso disfrazado de éxito).
- `design_source`: `generated` | `user_overlay` | `user_img2img`.

### Video
- Render: Shotstack (`stage` sandbox o `v1` producción).
- Modos de generación (`video_gen_mode`): `full` = Venice genera un clip completo; `scenes` = Venice anima cada toma y Shotstack las une; `still` = stills + Ken Burns sin video AI.
- Modelos Venice: Seedance 2.5 / 2.0, Kling O3, MiniMax H3 (aliases resueltos en `venice_video_models.py`).
- Voz: fal Kokoro Spanish (típico en dev), ElevenLabs u OpenAI TTS.
- Clips propios (`user_clip_reel`): Drive cloud sin máster local — audio-only STT → VideoProducer (N tomas) → `pending_takes` → ffmpeg seek de shorts → Shotstack.
- URLs públicas: ngrok / `PUBLIC_IMAGE_BASE_URL` obligatorio para Meta y assets locales; fondos fal pueden ir a Shotstack como URLs `fal.media`.

---

## 9. Publicación social y HITL

### Redes
- Instagram / Meta (feed, stories, Reels) vía Graph API y sidecar Go.
- LinkedIn nativo **solo desde Python**: API versionada `/rest/images` + `/rest/posts` con header `LinkedIn-Version`. Solo imagen y solo perfil personal; el token dura ~60 días sin refresh automático (la UI avisa a ≤7 días).
- TikTok: **sin publicación automática** hasta App Review — se genera la pieza.
- X: publicación nativa (OAuth 1.0a, tweet + imagen).
- Multi-cuenta: N cuentas por proveedor; el run elige `social_account_id` (Cuenta destino).

### Human-in-the-loop
- Estados relevantes: `queued` → `running` → (`pending_takes` en clips Drive) → `pending_approval` → aprobado / rechazado / regenerado.
- Clips: aceptar/descartar/reordenar tomas → render → aprobar MP4.
- Acciones MP4: Aprobar, Rechazar, Solicitar cambios (`revise`).
- Una revisión **nunca publica sola**: vuelve a HITL.

### Limitación actual de “Solicitar cambios”
La UI y el endpoint están conectados. Mejoras 2026-09:

- notas de **escena/personas** van al inicio del prompt (`compose_visual_prompt`) y pueden **auto-activar** Venice/fal edit sobre foto real;
- tipografía sigue siendo Pillow (la IA de edit no debe pintar letras).

Pendiente: pasar notas al copywriter de forma específica; ajustar color/contraste del overlay solo con notas tipográficas.

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
| POST | `/runs/sync`, `/runs/async` | Ejecutar pipeline (`drive_folder_id`, `editing_goal`, `take_count` en clips) |
| GET/POST | `/runs/{id}/takes`, POST `.../takes/render` | HITL de tomas (`pending_takes`) |
| GET | `/media/drive/{file_id}` | Preview corto autenticado (`start_s`/`end_s`) |
| POST | `/runs/{id}/approve\|reject\|revise` | HITL del MP4 / pieza |
| GET | `/runs`, `/runs/{id}` | Historial / estado |
| POST/GET | `/campaigns`, POST `.../fire` | Scheduler |
| GET | `/auth/login/{provider}`, callbacks, `/auth/accounts` | OAuth multi-cuenta |
| POST | `/auth/register`, `/auth/login` | SaaS email (si `STAGING_SAAS_ENABLED`) |
| GET | `/auth/me` | Perfil + créditos (JWT) |
| GET | `/billing/credits`, `/billing/bold-checkout` | Saldo / firma Bold |
| POST | `/billing/bold-webhook` | Confirmación de pago Bold |

Swagger local: `http://127.0.0.1:8000/docs`.

---

## 11. Frontend (dashboard)

- Con **SaaS** (`VITE_STAGING_SAAS=true`): `/` = landing, `/login` = registro/login, `/app` = estudio.
- Campo de brief: “Descripción del producto o evento”.
- **Red social** y **Formato de publicación**: dos selects acoplados alimentados por `/image/formats`; al cambiar de red se corrige el formato si dejó de ser válido.
- Video (solo en `reel`): modo de generación y modelo Venice. En `user_clip_reel`: carpeta Drive, objetivo de edición, N tomas, auto/manual.
- Selector de generador de imagen (fal / Venice / SD según keys).
- Upload de manual de marca con preview de paleta y logos.
- Upload de foto + toggle alterar con IA (Venice edit preferido; `design_source` visible).
- Indicaciones visuales solo de escena; tipografía vía Pillow.
- Selector de cuenta destino, enlace opcional, CTA en imagen opcional.
- Modo interactivo + hilo de pensamiento en vivo de los agentes.
- Sync / Async, historial, Integraciones OAuth (Meta / LinkedIn / X / **Google Drive**), burbuja del Asesor.

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
| Venice.ai imagen / escenas + **edit foto real** | Hecho (`user_img2img`; sin `quality` en `/image/edit`) |
| Asesor creativo | Hecho |
| Sidecar Go | Hecho |
| Hilo de pensamiento + modo interactivo | Hecho |
| Contraste tipográfico adaptativo | Hecho |
| Formatos por red + universal 1:1 | Hecho (diseño) |
| Kubernetes / Skaffold | Escrito, sin clúster real |
| Canva / Figma MCP | Pendiente |
| Publicación nativa TikTok | Pendiente (App Review) |
| Publicación nativa X | Hecho (OAuth 1.0a) |
| Revise que mueva copy + overlay / escena | Parcial (auto-edit si notas piden personas) |
| Error de LLM visible en UI | Pendiente |

---

## 15. Deuda y riesgos operativos

1. Stub silencioso del LLM si Ollama/API falla → copy genérico sin aviso claro en UI.
2. Meta/Instagram: scopes OAuth, tokens de Página, ngrok con dominio estable.
3. Reels: sin worker `video_render` el job queda encolado para siempre.
4. Canva OAuth y plantillas MCP no implementados.
5. CI/CD K8s no estrenado en GKE real.
6. Video v2 pendiente: música de fondo, captions por palabra; bucket S3/GCS opcional (hoy Drive del cliente + audio-only).
7. TikTok: la pieza se genera; publish tras App Review. X ya publica nativo.
8. El formato `universal` cubre solo imagen; los reels siguen siendo 9:16 por red.
9. LinkedIn: sin refresh automático del token (~60 días) y sin páginas de empresa.
10. Integraciones UI: Conectar Meta / LinkedIn / X / **Google Drive**.

---

## 16. Cómo conectar Google Drive (GOOGLE_CLIENT_ID) — paso a paso

Este capítulo es la guía operativa para que el dashboard pueda usar **Conectar Google Drive** y el formato `user_clip_reel`. Sin estas variables, la API responde `GOOGLE_CLIENT_ID no configurado en .env`.

### Qué hace la app (comportamiento real del código)

1. El usuario pulsa **Conectar Google Drive** en Integraciones → el frontend abre `GET /api/auth/login/google`.
2. El backend redirige a Google OAuth con:
   - Scope: `https://www.googleapis.com/auth/drive.readonly` (solo lectura).
   - `access_type=offline` y `prompt=consent` (obligatorio para obtener `refresh_token`; el worker Celery refresca el token sin UI).
3. Google vuelve a `GOOGLE_REDIRECT_URI` → `GET /api/auth/callback/google` intercambia el `code` por tokens y los guarda en la cuenta del tenant.
4. El frontend vuelve a `OAUTH_SUCCESS_REDIRECT_URL` (típico: `http://localhost:5173/`).
5. Con Drive conectado, un run `user_clip_reel` usa el token para listar/stream audio de la carpeta `drive_folder_id` (sin bajar el máster completo).

### Variables de entorno (`.env` en la raíz del proyecto)

```
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxx
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/callback/google
OAUTH_SUCCESS_REDIRECT_URL=http://localhost:5173/
```

Producción (ejemplo dominio real del producto):

```
GOOGLE_REDIRECT_URI=https://marketing.powerupsecosistem.online/api/auth/callback/google
OAUTH_SUCCESS_REDIRECT_URL=https://marketing.powerupsecosistem.online/
```

Regla crítica: el **Authorized redirect URI** en Google Cloud Console debe coincidir **carácter a carácter** con `GOOGLE_REDIRECT_URI` (incluye `http` vs `https`, puerto `:8000`, y el path `/api/auth/callback/google`).

### Paso A — Crear proyecto y credenciales en Google Cloud

1. Entra a [Google Cloud Console](https://console.cloud.google.com/).
2. Crea o selecciona un proyecto (p. ej. `marketing-depa-ia`).
3. **APIs y servicios → Biblioteca** → busca **Google Drive API** → **Habilitar**.
4. **APIs y servicios → Pantalla de consentimiento OAuth**:
   - Tipo de usuario: **Externo** (salvo que uses solo Google Workspace interno).
   - Nombre de la app, email de soporte, dominio de desarrollador.
   - Scopes: añade `.../auth/drive.readonly` (o el scope completo `https://www.googleapis.com/auth/drive.readonly`).
   - En modo **Testing**: añade como **usuarios de prueba** los Gmail que van a conectar Drive (si no, Google bloquea el consentimiento fuera de la lista).
   - Nota: para usuarios fuera de Testing en producción, Google puede exigir **verificación** de la app por el scope sensible de Drive (días/semanas). En desarrollo local basta Testing + test users.
5. **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**:
   - Tipo de aplicación: **Aplicación web**.
   - Nombre: p. ej. `Marketing DEPA IA local`.
   - **URI de redirección autorizados** (añade los que uses):
     - Local: `http://localhost:8000/api/auth/callback/google`
     - Prod: `https://marketing.powerupsecosistem.online/api/auth/callback/google`
   - Guarda → copia **Client ID** y **Client Secret**.

### Paso B — Pegar en `.env` y reiniciar API

1. Copia `.env.example` a `.env` si aún no existe.
2. Rellena `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`.
3. Reinicia Uvicorn (el gateway lee settings al arrancar; si hay workers zombi en `:8000`, mátalos y deja uno solo).
4. Verifica: abrir `http://127.0.0.1:8000/api/auth/login/google` debe redirigir a `accounts.google.com` (no devolver error 400 de client id vacío).

### Paso C — Conectar desde el dashboard

1. Stack mínimo: Postgres+Redis, Uvicorn `:8000`, frontend Vite (`:5173`).
2. Dashboard → **Integraciones** → botón **Conectar Google Drive** (o **Reconectar** si ya había cuenta).
3. Elige la cuenta Google de prueba → acepta acceso de solo lectura a Drive.
4. Debes volver al dashboard sin error OAuth; en Integraciones debe figurar el proveedor `google` como conectado.
5. Si el token no trae `refresh_token`, vuelve a pulsar **Reconectar Google Drive** (el login fuerza `prompt=consent`).

### Paso D — Usar clips (`user_clip_reel`)

1. En Google Drive, abre la carpeta con los videos → la URL suele ser `https://drive.google.com/drive/folders/FOLDER_ID` → copia el `FOLDER_ID`.
2. En el brief: formato **Video con mis clips** / `user_clip_reel`, pega el ID, define objetivo de edición y N tomas.
3. Necesitas también: worker Celery `-Q video_render`, `ffmpeg` en PATH, `STT_PROVIDER=whisper` (o mock en tests).
4. Flujo: propose → `pending_takes` → render → `pending_approval`.

### Fallos frecuentes

| Síntoma | Causa probable | Qué hacer |
|---------|----------------|-----------|
| `GOOGLE_CLIENT_ID no configurado` | `.env` vacío o API sin reiniciar | Rellenar vars y reiniciar Uvicorn |
| `redirect_uri_mismatch` | URI en Console ≠ `GOOGLE_REDIRECT_URI` | Igualar ambas al milímetro |
| Pantalla “app no verificada” / acceso denegado | Usuario no está en test users | Añadir el Gmail en Testing |
| Drive conecta pero Celery falla al listar | Sin `refresh_token` | Reconectar con consent; verificar `access_type=offline` en login |
| Carpeta vacía / 404 | `drive_folder_id` incorrecto o sin videos | ID de carpeta, no de archivo; compartir/acceso con la misma cuenta OAuth |
| PyJWT / módulo jwt | Dependencia ausente en venv | `pip install PyJWT` (ya en `requirements.txt`) |

### Checklist rápido (copiar a NotebookLM / ops)

- [ ] Drive API habilitada en el proyecto GCP
- [ ] OAuth consent screen + scope `drive.readonly` + test users
- [ ] Client ID web + redirect URI exacto
- [ ] `.env` con las tres vars Google + redirect frontend
- [ ] Uvicorn reiniciado
- [ ] Integraciones → Conectar Google Drive OK
- [ ] `ffmpeg` + worker `video_render` listos para el primer reel de clips

---

## 17. Capa SaaS (landing + login + Bold + créditos)

Flags duales (ambos necesarios):

| Variable | Capa | Notas |
|----------|------|--------|
| `STAGING_SAAS_ENABLED=true` | API | Auth email, billing, cobro de créditos |
| `VITE_STAGING_SAAS=true` | Frontend **build** | Rutas `/`, `/login`, `/app`; en Docker es build-arg — rebuild obligatorio |

Flujo: landing → registro/login (JWT) → estudio → comprar créditos (Bold webhook) → publicar descuenta créditos (402 si no hay saldo).  
Contraseñas: PBKDF2 120k, irreversibles. Guía: `docs/staging-landing-bold.md`.

---

## 18. Glosario rápido

| Término | Significado |
|---------|-------------|
| Brief | Entrada de campaña (tema, público, red, objetivo, tono) |
| HITL | Human-in-the-loop: aprobación humana antes de publicar |
| Brand campaign piece | Layout canónico cuando hay manual de marca |
| video_render | Cola Celery dedicada a renders de video |
| Design-as-Code | Foto del usuario como capa base + overlay programático |
| `user_img2img` | Foto editada con Venice/fal (escena) + tipografía Pillow |
| Inbound | Marco Attract→Convert→Close→Delight + pirámide de fines en redes |
| Formato universal | Pieza 1080×1080 que encaja en todas las redes sin recortes |
| SaaS / staging SaaS | Landing + login email + créditos Bold (flags STAGING/VITE) |
| Hilo de pensamiento | Stream de eventos de los agentes por `trace_id`, con checkpoints interactivos |
| `GOOGLE_CLIENT_ID` | ID de cliente OAuth web de Google Cloud para Conectar Google Drive |
| `drive.readonly` | Scope OAuth: lectura de Drive; no escribe ni borra archivos |
| `pending_takes` | HITL de tomas antes de renderizar el MP4 de clips |

---

## 19. Preguntas útiles para hacerle a NotebookLM

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
- **Dame el paso a paso exacto para obtener y configurar GOOGLE_CLIENT_ID y conectar Google Drive en local (y qué cambia en producción).**
- Si aparece `redirect_uri_mismatch`, ¿qué debo comparar y corregir?
- Tras conectar Drive, ¿cómo obtengo el `drive_folder_id` y cuál es el flujo `pending_takes`?

---

## 20. Resumen ejecutivo

Marketing DEPA IA es un MVP local completo para generar copy e identidades visuales con agentes, respetar un brand book (OCR + paleta + logos), **editar fotos reales del local con Venice** (escena) y tipografía Pillow, producir Reels o clips desde Drive (cloud + HITL de tomas), elegir el formato correcto de cada red (o uno universal) y publicar con control humano en Meta, LinkedIn o X. Lo más maduro es generación + marca + foto real + formatos + HITL + multi-cuenta + OAuth Google Drive. TikTok se genera; publish tras App Review.
