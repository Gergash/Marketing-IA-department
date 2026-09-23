# Staging E2E — Login Auth0 → publicar en red

Flujo local completo del departamento (opción A: SQLite, sin Docker Redis/Celery).

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

## Qué no cubre opción A

- Reels async (Redis + Celery `video_render`)
- Bold webhook real

Ver: [`auth0.md`](auth0.md), [`staging-landing-bold.md`](staging-landing-bold.md), [`manual-staging.md`](manual-staging.md).
