# Capa SaaS — Marketing DEPA IA

Landing, registro/login por correo (único), botón Bold y créditos para publicar en redes.

Guía larga (manual local + ngrok): [`manual-staging.md`](manual-staging.md).

## Activar

### 1. Backend

Copia variables de `.env.staging.example` a `.env` (local) o `.env.production` (VPS):

```bash
STAGING_SAAS_ENABLED=true
JWT_SECRET=un-secreto-largo-aleatorio   # obligatorio en prod; no dejar vacío
JWT_TTL_MINUTES=10080
BOLD_API_KEY=<llave identidad Bold>
BOLD_INTEGRITY_SECRET=<llave secreta Bold>
BOLD_WEBHOOK_SECRET=<misma llave secreta>
PACK_AMOUNT_COP=99000
CREDITS_PER_PACK=100
STAGING_SUCCESS_REDIRECT_URL=http://localhost:5173/app?paid=1
# Prod:
# STAGING_SUCCESS_REDIRECT_URL=https://marketing.powerupsecosistem.online/app?paid=1
```

SQLite/Postgres crean tablas `app_users`, `credit_wallets` y `payment_records` al iniciar (`schema_patches`).

### 2. Frontend (bake-time)

El flag de UI **no** se lee del `.env` de la API en runtime. Vite lo hornea en el build.

**Local** — `frontend/.env.local`:

```bash
VITE_STAGING_SAAS=true
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
| `/login` | Registro o login (email único) |
| `/app` | Estudio de marketing (dashboard) |

Tras **registro exitoso** o login, la UI muestra el **botón Bold** para comprar el paquete de créditos.

## Auth

| Pieza | Detalle |
|-------|---------|
| Hash | PBKDF2-HMAC-SHA256, 120 000 iteraciones — **irreversible** |
| Token | JWT (`sub`=email, `tenant_id`); default TTL 7 días |
| Legacy | Con `STAGING_SAAS_ENABLED=false`, sigue `API_KEY` Bearer |

No existe (aún) recuperación pública de contraseña ni rate limiting en login/registro. Un panel admin puede forzar reset sin exponer el hash en claro.

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

- `POST /api/auth/register` — email, password, full_name
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/billing/credits`
- `GET /api/billing/bold-checkout` — firma integridad Bold (JWT)
- `POST /api/billing/bold-webhook`

## Producción (estado actual)

SaaS puede ir **activo** en `marketing.powerupsecosistem.online` con ambos flags en `true` y frontend reconstruido.

Checklist:

1. `STAGING_SAAS_ENABLED=true` + `JWT_SECRET` fuerte en `.env.production`
2. `VITE_STAGING_SAAS=true` (build-arg) → `docker compose … up -d --build frontend`
3. Llaves Bold + webhook HTTPS del dominio
4. Hard refresh del navegador tras el rebuild

Con SaaS off (`STAGING_SAAS_ENABLED=false` y rebuild con `VITE_STAGING_SAAS=false`), el modo legacy con `API_KEY` sigue disponible.
