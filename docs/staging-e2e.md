# Staging E2E — Login Auth0 → publicar en red

Actualizado: **2026-10-03**. Flujo local completo del departamento (opción A: SQLite, sin Docker Redis/Celery). El **agente de DMs** sí necesita Redis + Celery: ver [Agente de DMs en staging local](#agente-de-dms-en-staging-local).

Estado canónico del proyecto: [`../estado-actual.txt`](../estado-actual.txt).

## Quick path

1. API `:8000` + Vite `:5173` + go-publisher `:8088` + túnel HTTPS (Meta)
2. Login Auth0 en `/login` → `/app` con créditos semilla (`STAGING_SEED_CREDITS`)
3. Brief → Generar (HITL) → Aprobar → publicación Instagram vía Page token o Conectar Meta
4. Meta Live App Review: **solo con flag explícito** (sigue en espera)

## Servicios (deben estar arriba)

| Pieza | Comando / check |
|-------|-----------------|
| API | `uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000 --reload` → `/api/health` |
| UI | `cd frontend && npm run dev` → `http://localhost:5173/` |
| Go Meta | `cd microservices/social-publisher-go && go run ./cmd/server` → `:8088/health` |
| Túnel | `cloudflared tunnel --url http://127.0.0.1:8000` (o ngrok) → pegar URL en `PUBLIC_IMAGE_BASE_URL` |

Tras reiniciar el túnel, **actualiza** `PUBLIC_IMAGE_BASE_URL` en `.env` y reinicia/recarga la API.

## Auth0

- FE: `VITE_STAGING_SAAS` + `VITE_AUTH0_*` en `frontend/.env.local`
- BE: `STAGING_SAAS_ENABLED` + `AUTH0_*` + `ADMIN_EMAILS`
- Primer login crea `AppUser` + wallet (`STAGING_SEED_CREDITS`, default 100)
- Si el wallet queda en 0, el siguiente login Auth0 lo rellena (solo staging)
- Usa **Continuar con Auth0** / **Crear cuenta** (no armes `/u/signup` a mano)

## OAuth redes (Auth0)

**Conectar** Meta/LinkedIn/X/Drive debe ir con Bearer Auth0: la SPA pide
`GET /api/auth/login/{provider}` → JSON `{ "authorize_url" }` → redirige al proveedor.
Un `window.location` directo al API (sin JWT) responde `Autenticación Auth0 requerida.`

En developers registra **ambas** URIs (prod + localhost) si pruebas en local.
El `.env` canónico y el compose de prod usan solo `marketing.powerupsecosistem.online`
para que un merge/pull en la VPS no desincronice callbacks.
Overrides locales: `.env.staging.local` (gitignored).

| Proveedor | URI prod (canónica) | URI local opcional |
|-----------|---------------------|--------------------|
| **LinkedIn** | `https://marketing.powerupsecosistem.online/api/auth/callback/linkedin` | `http://localhost:8000/api/auth/callback/linkedin` |
| **X** | `…/api/auth/callback/x` | `http://localhost:8000/api/auth/callback/x` |
| **Meta** | `…/api/auth/callback/meta` | `http://localhost:8000/api/auth/callback/meta` |
| **Google** | `…/api/auth/callback/google` | `http://localhost:8000/api/auth/callback/google` |

Errores típicos: LinkedIn *"redirect_uri does not match"* · X *"Callback URL not approved" (415)* → la URI del portal ≠ la activa en el API.

## OAuth / Meta local

```env
OAUTH_SUCCESS_REDIRECT_URL=http://localhost:5173/app
META_REDIRECT_URI=http://localhost:8000/api/auth/callback/meta
# … mismas URIs en Meta Developers
```

**Atajo IG:** con `META_PAGE_ACCESS_TOKEN` + `INSTAGRAM_BUSINESS_ACCOUNT_ID` el approve publica **sin** Conectar Meta.

Imagen feed: aspect ratio válido (ideal **1:1** 1080×1080). Meta error `36003` = ratio inválido.

## Checklist E2E

- [x] Health API + Go + Vite
- [x] Túnel HTTPS sirve `/static/images/*`
- [x] go-publisher publica en Instagram (Page token)
- [x] Créditos staging ≥ 100 (debitan al aprobar)
- [x] Pipeline brief → `pending_approval` → approve → `completed` + post IG
- [ ] Login Auth0 UI → `/app` (credenciales del usuario en Universal Login)
- [ ] Desde UI: Generar → Aprobar → completed
- [x] Agente de DMs: API + worker + Redis + Vite arriba, webhook verifica el token, tablas `dm_*` creadas
- [ ] Agente de DMs: Conectar Meta (scopes de mensajería) → activar agente → DM simulado aparece en la Bandeja con respuesta

## Agente de DMs en staging local

La Bandeja de DMs y el agente se prueban en local con DMs **simulados** (sin configurar Meta) o reales (con túnel).

### 1. Variables en `.env.staging.local`

La API solo lee `.env`; los overrides de `.env.staging.local` se pasan al arrancar (paso 2). Bloque necesario:

```env
LLM_PROVIDER=openai                      # .env local tiene ollama; el agente usa OpenRouter como prod
OPENAI_API_BASE=https://openrouter.ai/api/v1
OPENAI_MODEL=nvidia/nemotron-3-super-120b-a12b:free
OPENAI_MODEL_FALLBACKS=google/gemma-4-26b-a4b-it:free,dots-studio/dots-3-note-preview:free
LLM_MAX_RETRIES=3
OPENROUTER_DISABLE_REASONING=true
META_WEBHOOK_VERIFY_TOKEN=<texto aleatorio>
DM_DEBOUNCE_SECONDS=4
DM_AGENT_DRY_RUN=true                    # guarda la respuesta en la Bandeja sin enviarla a Meta
```

`OPENAI_API_KEY` (OpenRouter) y `META_CLIENT_SECRET` se toman del `.env`.

### 2. Servicios (Git Bash, raíz del repo)

```bash
# Redis
docker compose -f infra/docker-compose.yml up -d redis

# API con overrides de staging
.venv/Scripts/python.exe -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000 --reload --env-file .env.staging.local

# Worker (otra terminal): mismas variables
set -a && source .env.staging.local && set +a
.venv/Scripts/python.exe -m celery -A workers.celery_app.celery_app worker -l info -P threads -c 4 --without-gossip --without-mingle --without-heartbeat

# Frontend (otra terminal)
cd frontend && npm run dev
```

Comprobaciones: `/api/health` → 200 · `/api/inbox/accounts` sin login → 401 · el banner del worker lista `workers.tasks.handle_dm_task`.
Al arrancar con SQLite se crean `dm_contacts` / `dm_messages` y la columna `oauth_tokens.dm_agent_enabled`.

### 3. Probar con DMs simulados

1. `http://localhost:5173` → login Auth0 → **Integraciones → Conectar Meta**. `marketing_staging.db` arranca **sin cuentas Meta**; reconectar concede `instagram_manage_messages`, `pages_messaging`, `pages_manage_metadata`.
2. **Bandeja de DMs** → activar el interruptor del agente en la cuenta.
3. Simular la conversación:

```bash
.venv/Scripts/python.exe scripts/simulate_dm.py "Hola, quiero cotizar un apartamento"
.venv/Scripts/python.exe scripts/simulate_dm.py "Me llamo Ana, vivo en Laureles"
.venv/Scripts/python.exe scripts/simulate_dm.py "Hola" --sender otra-persona      # otra conversación
.venv/Scripts/python.exe scripts/simulate_dm.py "Hola" --platform messenger       # por page_id
```

Tras `DM_DEBOUNCE_SECONDS` + la respuesta del LLM, la Bandeja (polling 20 s o **Refrescar**) muestra contacto, motivo, categoría y la respuesta del agente; la primera vez que pide datos incluye el enlace `/privacidad`.
Si el script dice "agente APAGADO", activa el interruptor en la cuenta.

### 4. Probar con DMs reales (opcional)

1. `cloudflared tunnel --url http://127.0.0.1:8000`
2. Meta Developers → Webhooks: callback `https://<url-túnel>/api/webhooks/meta`, verify token = `META_WEBHOOK_VERIFY_TOKEN`, campo `messages` en Page e Instagram.
3. `DM_AGENT_DRY_RUN=false` y reiniciar API + worker.
4. Escribir desde una cuenta **con rol en la app** (tester), distinta de la que recibe: en modo Development Meta no entrega DMs de otras personas.

La URL del túnel cambia en cada arranque. Al desplegar, el callback del webhook debe volver a `https://marketing.powerupsecosistem.online/api/webhooks/meta`.

## Qué no cubre opción A

- Reels async (Redis + Celery `video_render`)
- Agente de DMs (Redis + Celery cola `celery`; ver sección anterior)
- Bold webhook real

Ver: [`auth0.md`](auth0.md), [`staging-landing-bold.md`](staging-landing-bold.md), [`manual-staging.md`](manual-staging.md).
