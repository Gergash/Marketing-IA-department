# Capa SaaS — Marketing DEPA IA

Landing, **Auth0 Universal Login** (única identidad), botón Bold y créditos para publicar en redes.

**Estado (2026-09-23):** Auth0-only E2E local OK hasta publicar en Instagram. Checklist: [`staging-e2e.md`](staging-e2e.md). Identidad: [`auth0.md`](auth0.md). Panel: [`admin-panel.md`](admin-panel.md). Snapshot 17-sep: [`estado-saas-auth0-2026-09-17.md`](estado-saas-auth0-2026-09-17.md). Manual largo: [`manual-staging.md`](manual-staging.md).

## Activar

### 1. Backend

Copia variables de `.env.staging.example` a `.env` (local) o `.env.production` (VPS):

```bash
STAGING_SAAS_ENABLED=true
AUTH0_DOMAIN=dev-ayl6gsakmvf7rb27.us.auth0.com
AUTH0_CLIENT_ID=loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L
AUTH0_AUDIENCE=                         # vacío = valida ID token (aud = client_id)
ADMIN_EMAILS=info@powerupsagencia.com
ADMIN_PANEL_ENABLED=true
BOLD_API_KEY=<llave identidad Bold>
BOLD_INTEGRITY_SECRET=<llave secreta Bold>
BOLD_WEBHOOK_SECRET=<misma llave secreta>
PACK_AMOUNT_COP=99000
CREDITS_PER_PACK=100
STAGING_SUCCESS_REDIRECT_URL=http://localhost:5173/app?paid=1
# Prod:
# STAGING_SUCCESS_REDIRECT_URL=https://marketing.powerupsecosistem.online/app?paid=1
```

`JWT_SECRET` quedó en `.env.example` por legado; **ya no autentica** usuarios SaaS si Auth0 está configurado.

SQLite/Postgres crean tablas `app_users`, `credit_wallets` y `payment_records` al iniciar (`schema_patches`).

### 2. Frontend (bake-time)

El flag de UI **no** se lee del `.env` de la API en runtime. Vite lo hornea en el build.

**Local** — `frontend/.env.local`:

```bash
VITE_STAGING_SAAS=true
VITE_AUTH0_DOMAIN=dev-ayl6gsakmvf7rb27.us.auth0.com
VITE_AUTH0_CLIENT_ID=loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L
```

**Prod (Docker)** — `infra/docker-compose.prod.yml` pasa el build-arg:

```yaml
args:
  VITE_API_URL: ""
  VITE_STAGING_SAAS: ${VITE_STAGING_SAAS:-true}
```

Tras cambiar `VITE_STAGING_SAAS` en el VPS hay que **rebuild** el contenedor `frontend`. Reiniciar solo `api` no activa landing/login.

### 3. Rutas

| URL | Pantalla |
|-----|----------|
| `/` | Landing del departamento de marketing agéntico |
| `/login` | Auth0 Universal Login (única identidad; `/register` API → 410) |
| `/app` | Estudio (Bearer ID token Auth0) |
| `/admin` | Panel administrador (`ADMIN_EMAILS` / `is_admin`) |

Rutas desconocidas (`/ladmin`, `/foo`) vuelven a la landing; no abren el estudio.

Tras login Auth0, la UI muestra el **botón Bold** para comprar el paquete de créditos (si hay claves Bold).

## Auth

| Pieza | Detalle |
|-------|---------|
| IdP | Auth0 Universal Login — **única** vía de registro/login SaaS |
| Token | ID token RS256 (JWKS). La SPA lo manda como `Authorization: Bearer` |
| Local legado | `POST /api/auth/register` y `/login` → **410 Gone** |
| Reset | Auth0 Dashboard / Forgot password. El panel admin **no** genera claves locales (410) |
| Admin | Email en `ADMIN_EMAILS` o `is_admin=true` |
| Legacy API | Con `STAGING_SAAS_ENABLED=false` (y Auth0 no configurado), sigue `API_KEY` Bearer |

No abrir `https://{tenant}.auth0.com/u/signup` a mano ni refrescar esa URL: aparece `some body keys are invalid`. Siempre partir de `/login` en la app (`/authorize`).

Friendly Name visible (“Sign Up to …”): Auth0 Dashboard → Settings → General. El hostname `dev-ayl6gsakmvf7rb27` no cambia sin Custom Domain.

## Bold + webhook

1. Panel Bold → Webhook: `https://<dominio>/api/billing/bold-webhook` (local: ngrok → `:8000`)
2. `BOLD_WEBHOOK_SECRET` = misma llave secreta del botón.
3. Referencia de orden: `MDIA-{tenant_id}-{timestamp}` — el webhook acredita `CREDITS_PER_PACK`.

**Importante:** si `BOLD_WEBHOOK_SECRET` / `BOLD_INTEGRITY_SECRET` quedan vacíos, la validación de firma puede saltarse — no dejes secretos vacíos en prod.

## Créditos por publicación

| Tipo | Créditos |
|------|----------|
| Imagen estática | 1 |
| Imagen IA o diseño sobre foto del usuario | 2 |
| Video con subtítulos | 5 |
| Reel / clip IA | 8 |

Sin saldo suficiente al publicar → **402 Payment Required**.

## Endpoints

- `GET /api/auth/me` — perfil + `is_admin` + `auth0_sub` (Bearer Auth0)
- `POST /api/auth/register` · `POST /api/auth/login` — **410** (usar Auth0)
- `GET /api/billing/credits`
- `GET /api/billing/bold-checkout` — firma integridad Bold
- `POST /api/billing/bold-webhook`
- `/api/admin/*` — ver [`admin-panel.md`](admin-panel.md)

## Producción (estado actual)

SaaS **UI** puede estar activa en `marketing.powerupsecosistem.online` (flags VITE bake, commit `9fe9e15`). **Auth0 en prod no está cableado**: la app Auth0 solo tiene callback `http://localhost:5173`. Hasta añadir el dominio prod en Auth0 + rebuild con `VITE_AUTH0_*`, el login de producción no es este flujo.

Checklist cuando se despliegue Auth0 a VPS:

1. Callbacks / logout / web origins: `https://marketing.powerupsecosistem.online`
2. `.env.production`: `AUTH0_*` + `ADMIN_EMAILS` + `STAGING_SAAS_ENABLED=true`
3. Rebuild frontend con `VITE_STAGING_SAAS` + `VITE_AUTH0_DOMAIN` + `VITE_AUTH0_CLIENT_ID`
4. Llaves Bold + webhook HTTPS del dominio
5. Hard refresh del navegador tras el rebuild

Con SaaS off (`STAGING_SAAS_ENABLED=false` y rebuild con `VITE_STAGING_SAAS=false`), el modo legacy con `API_KEY` sigue disponible.
