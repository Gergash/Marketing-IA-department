# Snapshot 2026-09-17 — SaaS Auth0, panel admin y espera de Meta Live

Este archivo es el inventario detallado del workstream SaaS/Auth0/admin (sesión 17 sep 2026, noche). **Meta App Review / Live no se toca hasta que el usuario dé la bandera explícita.**

**Quién lo usa:** operador, el siguiente agente, o un revisor que necesita saber qué hay en disco vs qué hay en `origin/main`.

## Quick path

1. Identidad SaaS = **solo Auth0**. Login/registro local (email+password+JWT propio) está **eliminado** (`410` en `/api/auth/register|login`).
2. Panel `/admin` lee tablas **propias** (`app_users`, `payment_records`, `api_usage_events`, `credit_wallets`), no Auth0 Management ni Venice/fal dashboards.
3. En local, el admin `info@powerupsagencia.com` **ya se registró** vía Universal Login y entra al estudio (`/app`).
4. **Producción Meta Live: no iniciado.** Guía existente: [`infra/deploy/meta-oauth-production.md`](../infra/deploy/meta-oauth-production.md). Esperar bandera.

## Estado Git (2026-09-17 ~22:30 COT)

| Hecho | Valor |
|-------|--------|
| Rama | `main` |
| HEAD commit | `d422a6e` *docs: plan de migracion a gpt-image-2 directo contra OpenAI* |
| Tracking | `origin/main` **ahead 4** (commits aún no pusheados) |
| `master` | `ecbe53e` — rama estable; **no fusionar** hasta que se pida |
| Auth0-only | **Working tree**, no está en HEAD. Hay que committear cuando se pida |

### Los 4 commits locales (aún no en origin)

| SHA | Qué hizo |
|-----|----------|
| `9fe9e15` | Fix prod: `VITE_STAGING_SAAS` bake-time en `Dockerfile.frontend` + compose. Sin esto `/` era el dashboard legacy. |
| `42fb92c` | Docs de capa SaaS (landing/login/Bold) alineadas con bake-time. |
| `17a9bc0` | Panel admin `/admin`: KPIs, usuarios, pagos Bold, consumo por proveedor. Auth0-ready vía `tenant_id`. |
| `d422a6e` | Plan **documentado, no implementado** de gpt-image-2 directo vs Venice. |

### Working tree (Auth0-only + docs admin) — no committed

**Modificados**

| Área | Archivos |
|------|----------|
| Frontend Auth0 | `frontend/src/main.jsx`, `auth.js`, `LoginPage.jsx`, `App.jsx`, `StagingBar.jsx`, `BoldCheckout.jsx`, `AdminPanel.jsx`, `package.json`, `package-lock.json` |
| Gateway Auth0 | `gateway/app/core/auth.py`, `settings.py`, `api/auth_users.py`, `api/admin.py`, `models/entities.py`, `db/schema_patches.py` |
| Tests admin | `tests/test_admin_panel.py` |
| Docs | `docs/admin-panel.md`, `.env.example` |
| Skills ATL | `.atl/skill-registry.md`, `.atl/.skill-registry.cache.json` (ruido de registry, no es producto) |

**Nuevos (untracked)**

| Archivo | Rol |
|---------|-----|
| `gateway/app/services/auth0_jwt.py` | JWKS RS256 + upsert `AppUser` por `auth0_sub` |
| `tests/test_auth0_saas.py` | 410 local auth + upsert tenant/wallet |
| `docs/auth0.md` | Tenant, callbacks, flujo ID token |
| `frontend/.gitignore` | `.env.local`, estado MCP Auth0 |
| `docs/estado-saas-auth0-2026-09-17.md` | Este snapshot |

## Decisiones tomadas (innegociables en este workstream)

| Tema | Decisión | Por qué |
|------|----------|---------|
| IdP | Solo Auth0 Universal Login | El usuario pidió quitar sesión local |
| Token a la API | **ID token** (`getIdTokenClaims().__raw`), `aud` = `AUTH0_CLIENT_ID` | MCP no pudo crear Resource Server (`create:resource_servers`) |
| Registro local | `POST /api/auth/register` y `/login` → **410** | Evitar dos fuentes de identidad |
| Reset password admin | `POST /api/admin/users/{id}/reset-password` → **410** | Auth0 Dashboard / Forgot password |
| Panel admin | Independiente del IdP | Negocio = BD propia |
| Bootstrap admin | `ADMIN_EMAILS` (coma-separada) | Evita huevo-gallina `is_admin` |
| Rutas staging | Whitelist: `/`, `/login`, `/app`, `/admin`, legales | `/ladmin` caía a `App` **sin** Auth0 |
| Meta Live | **No tocar** hasta bandera | Pedido explícito 17-sep noche |

## Qué hay en runtime local (verificado con el usuario)

| Pieza | Estado 17-sep noche |
|-------|---------------------|
| Frontend Vite | `npm run dev` en `:5173` |
| Auth0 tenant | `dev-ayl6gsakmvf7rb27.us.auth0.com` |
| SPA | Marketing DEPA IA · client `loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L` |
| Callbacks / logout / web origins | `http://localhost:5173` (+ `/` en callbacks) |
| Signup admin | **OK** con `info@powerupsagencia.com` (tras error `some body keys are invalid` al abrir `/u/signup` a mano) |
| Estudio `/app` | **OK** con esa sesión |
| Panel `/admin` | Código listo. Requiere API gateway + `ADMIN_EMAILS` cargado (está en `.env`) |
| Bold | Claves vacías en `.env` local → no hay pagos reales; KPIs de ingresos en 0 |
| Consumo Venice/fal | Eventos solo tras **publicar** con `STAGING_SAAS_ENABLED` |

Contraseña de Auth0: **no está en el repo**. La elige el usuario al signup. `ADMIN_EMAILS` no es una clave.

Friendly Name del tenant Auth0: el usuario quería mostrar **PowerUps** en vez de `dev-ayl6gsakmvf7rb27`. Eso se cambia en Auth0 Dashboard → Settings → Friendly Name (no es código). El hostname Auth0 no cambia sin Custom Domain (pago).

## Arquitectura de identidad (cómo funciona de verdad)

```text
Usuario → /login → Auth0 Universal Login (/authorize, no /u/signup a pelo)
       → redirect localhost:5173
       → Auth0Provider (SPA, cache localStorage)
       → ID token Bearer en cada /api/*
       → gateway require_auth
            1. JWKS RS256, iss=https://{AUTH0_DOMAIN}/, aud=client_id
            2. upsert AppUser(auth0_sub, email) + CreditWallet
            3. tenant_id UUID corto
       → si email ∈ ADMIN_EMAILS o is_admin → /admin 200
```

### Archivos clave

| Capa | Path | Comportamiento |
|------|------|----------------|
| SPA provider | `frontend/src/main.jsx` | `Auth0Provider`; rutas protegidas `/app` `/admin`; unknown → landing |
| Token | `frontend/src/auth.js` | `getIdTokenClaims().__raw`; 401 → `/login` |
| Login UI | `frontend/src/LoginPage.jsx` | `loginWithRedirect` / `screen_hint=signup` |
| JWT | `gateway/app/services/auth0_jwt.py` | decode + upsert |
| Guard | `gateway/app/core/auth.py` | Auth0 primero si SaaS+AUTH0_*; API_KEY solo si Auth0 no está |
| Me | `gateway/app/api/auth_users.py` | `GET /me`; register/login 410 |
| Admin | `gateway/app/api/admin.py` | overview/users/payments/usage; reset 410 |
| Columna | `AppUser.auth0_sub` UNIQUE | `schema_patches.py` SQLite/Postgres |

### Variables

**Backend `.env`**

```env
STAGING_SAAS_ENABLED=true
AUTH0_DOMAIN=dev-ayl6gsakmvf7rb27.us.auth0.com
AUTH0_CLIENT_ID=loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L
AUTH0_AUDIENCE=          # vacío = ID token
ADMIN_EMAILS=info@powerupsagencia.com
ADMIN_PANEL_ENABLED=true
```

**Frontend `frontend/.env.local`** (gitignore)

```env
VITE_STAGING_SAAS=true
VITE_AUTH0_DOMAIN=dev-ayl6gsakmvf7rb27.us.auth0.com
VITE_AUTH0_CLIENT_ID=loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L
```

`VITE_*` es bake-time. En prod hay que rebuild del contenedor `frontend`.

## Panel de administrador — detección de datos

Fuente canónica de KPIs: [`admin-panel.md`](admin-panel.md). Resumen aquí para el snapshot.

| Superficie | Cómo “detecta” | Cuándo aparece vacío |
|------------|----------------|----------------------|
| Usuarios | Primera llamada API con ID token → fila `app_users` | Signup Auth0 sin entrar a la app |
| Pagos | Webhook Bold → `payment_records` | Sin `BOLD_*` o sin pago |
| Consumo Venice/fal/gpt-image-2 | `record_usage` al publicar/debitar | Nadie publicó en staging |
| Resumen | `GET /api/admin/overview` agrega las tres tablas | Lo anterior |

gpt-image-2 vía Venice se cuenta como proveedor **`venice`**, no como “openai”. Plan de ir directo a OpenAI: [`gpt-image-2-directo.md`](gpt-image-2-directo.md) (**no implementado**).

## Bugs encontrados y cierre

### 1. `/ladmin` abría el estudio sin Auth0

**Causa:** `resolvePage` hacía fallback a `App` para cualquier path desconocido. `isProtectedPath` solo cubría `/app` y `/admin`. `/ladmin` ≠ `/admin`.

**Fix:** whitelist de rutas staging; desconocidas → landing `/`. Archivo: `frontend/src/main.jsx`.

**Verificado conceptualmente:** `/admin` ahora redirige a `/login` si no hay sesión Auth0.

### 2. Signup `some body keys are invalid`

Página blanca en `…auth0.com/u/signup`. **No es el panel DEPA.** Causas típicas: refresh de `/u/signup` sin estado `/authorize`, Custom Login Page, o signup deshabilitado.

**Workaround que funcionó:** crear cuenta desde `http://localhost:5173/login` → **Crear cuenta** (`loginWithRedirect` + `screen_hint=signup`).

### 3. Prod sin landing (sesión anterior, ya commiteado)

`STAGING_SAAS_ENABLED` en API no basta. Vite hornea `VITE_STAGING_SAAS`. Fix en `9fe9e15`.

## Qué NO está hecho (explícito)

| Ítem | Estado |
|------|--------|
| Commit + push del Auth0-only | Pendiente (no se pidió commit) |
| Deploy Auth0 a VPS | Pendiente. Prod callbacks Auth0 aún no listados (hoy solo localhost:5173) |
| Resource Server Auth0 (access token + audience) | Denegado por scopes MCP; ID token es el diseño actual |
| Bold en local | Claves vacías |
| Tests e2e Auth0 reales (JWKS live) | Solo unitarios con upsert mock / 410 |
| Rate limit / MFA / Custom Domain | No |
| **Meta App Mode Live / App Review** | **Esperando bandera del usuario** |
| gpt-image-2 directo OpenAI | Solo doc |
| Fusionar `main` → `master` | No, hasta que se pida |

## Meta en producción — espera de bandera

Código de publicación Meta **ya existe** (OAuth + sidecar Go). Lo que falta es el trámite de **Meta Developers** (Live / App Review / usuarios reales fuera de roles de desarrollo).

| Ya documentado | Path |
|----------------|------|
| URLs prod, scopes, Basic Settings | [`infra/deploy/meta-oauth-production.md`](../infra/deploy/meta-oauth-production.md) |
| Orden redes + VPS | [`infra/deploy/proceso-integracion-redes.md`](../infra/deploy/proceso-integracion-redes.md) |
| App ID | `1258515492788752` |

Cuando llegue la bandera, el trabajo será de **portal Meta + `.env.production` + prueba Conectar Meta**, no de reescribir el publisher. Este snapshot no adelanta ese cambio.

## Cómo verificar el estado actual (local)

1. Frontend: `http://localhost:5173/` → landing.
2. `/login` → Auth0 → volver al estudio.
3. `/ladmin` → landing (no el estudio).
4. `/admin` sin sesión → `/login`.
5. Con `info@powerupsagencia.com` + API arriba → `/admin` KPIs (usuarios ≥ 1).
6. `POST /api/auth/register` → 410.

API local: hace falta Uvicorn en `:8000` leyendo el `.env` de la raíz (con `ADMIN_EMAILS`). Vite solo no sirve el overview.

## Mapa de docs (post este snapshot)

| Doc | Rol |
|-----|-----|
| [`estado-actual.txt`](../estado-actual.txt) | Cronología canónica del repo |
| [`auth0.md`](auth0.md) | Tenant, env, flujo token |
| [`admin-panel.md`](admin-panel.md) | KPIs y tablas |
| [`staging-landing-bold.md`](staging-landing-bold.md) | Landing + Bold + créditos (auth ahora Auth0) |
| [`manual-staging.md`](manual-staging.md) | Levantar staging local |
| [`gpt-image-2-directo.md`](gpt-image-2-directo.md) | Plan coste imagen, no código |
| Esta página | Diff Git + decisiones de la sesión Auth0 |

## Checklist para el siguiente turno

- [ ] Usuario da **bandera Meta Live** → seguir `meta-oauth-production.md` (no antes)
- [ ] Pedir commit del working tree Auth0 si se quiere historial limpio
- [ ] Añadir callbacks Auth0 de prod (`https://marketing.powerupsecosistem.online`) antes de deploy SaaS
- [ ] Rebuild frontend VPS con `VITE_AUTH0_*` + `VITE_STAGING_SAAS`
- [ ] Confirmar `ADMIN_EMAILS` en `.env.production`
- [ ] NotebookLM (`docs/notebooklm/…`) sigue fechado 2026-09-10; reindexar cuando se pida
