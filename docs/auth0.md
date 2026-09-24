# Auth0 — Marketing DEPA IA

Única identidad SaaS. El login/registro local (email + JWT propio) fue eliminado.

**Estado (2026-09-23):** E2E local verificado — Auth0 → estudio → créditos → Generar → Aprobar → Instagram. Checklist: [`staging-e2e.md`](staging-e2e.md). Snapshot histórico 17-sep: [`estado-saas-auth0-2026-09-17.md`](estado-saas-auth0-2026-09-17.md).

| Dato | Valor |
|------|--------|
| App SPA | Marketing DEPA IA |
| Domain | `dev-ayl6gsakmvf7rb27.us.auth0.com` |
| Client ID | `loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L` |
| Callbacks hoy | `http://localhost:5173/` (prod **aún no**) |
| Dashboard | [Application settings](https://manage.auth0.com/dashboard/us/dev-ayl6gsakmvf7rb27/applications/loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L/settings) |
| Users (IdP) | [User Management](https://manage.auth0.com/dashboard/us/dev-ayl6gsakmvf7rb27/users) |

## Variables

**Frontend** (`frontend/.env.local`, gitignored):

```env
VITE_STAGING_SAAS=true
VITE_AUTH0_DOMAIN=dev-ayl6gsakmvf7rb27.us.auth0.com
VITE_AUTH0_CLIENT_ID=loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L
```

**Backend** (`.env`):

```env
STAGING_SAAS_ENABLED=true
AUTH0_DOMAIN=dev-ayl6gsakmvf7rb27.us.auth0.com
AUTH0_CLIENT_ID=loXNtYYuNPxwCwuxDZv4i1cXAUWILw0L
AUTH0_AUDIENCE=   # vacío = valida ID token (aud = client_id)
ADMIN_EMAILS=info@powerupsagencia.com
ADMIN_PANEL_ENABLED=true
STAGING_SEED_CREDITS=100   # wallet al primer upsert (staging sin Bold)
```

Requisito: `PyJWT[crypto]` (paquete `cryptography`) para RS256.

## Flujo

1. `/login` → botones Auth0 (`loginWithRedirect`, signup con `screen_hint=signup`)
2. **No** pegar ni refrescar `https://…auth0.com/u/signup` a mano → error `some body keys are invalid`
3. SPA envía el **ID token** (`getIdTokenClaims().__raw`) como `Authorization: Bearer`
4. API valida JWKS RS256 (`auth0_jwt.py`), upsert `AppUser.auth0_sub` + email, `tenant_id` + wallet
5. Reloj Windows: backend ignora `iat` y usa leeway de `exp`; FE reintenta refresh del ID token

## Integraciones (redes)

«Conectar Meta/LinkedIn/X/Drive» **no** puede hacer `window.location` al API (no manda Bearer → 401).

Flujo correcto: `GET /api/auth/login/{provider}` con JWT → `{ "authorize_url" }` → redirect al portal.

Redirect URIs canónicas en `.env` = **prod** (`marketing.powerupsecosistem.online/...`). Overrides locales: `.env.staging.local`. Ver `GET /api/auth/oauth-config` e Integraciones en UI.

## Texto “Sign Up to dev-ayl6gsak…”

Eso es el **Friendly Name** del tenant Auth0, no un ID de la app. Dashboard → Settings → General → Friendly Name = `PowerUps`. El hostname `dev-ayl6gsakmvf7rb27.us.auth0.com` no cambia sin Custom Domain.

## Admin

Identidades Auth0 → [User Management](https://manage.auth0.com/). Negocio (usuarios sincronizados, pagos Bold, consumo Venice/fal) → `/admin`.

El correo admin **no tiene password en el repo**. Se registra en Auth0 con la contraseña que elija el operador. `ADMIN_EMAILS` solo marca el email como admin.

Detalle del flujo y del **Resumen**: [`admin-panel.md`](admin-panel.md).

## Nota API audience

El MCP actual no pudo crear un Resource Server (`create:resource_servers`). Hoy se valida el ID token. Si más adelante creas una API en Auth0, pon su identifier en `AUTH0_AUDIENCE` y en el `Auth0Provider` (`authorizationParams.audience`).

## Prod (pendiente)

Antes de desplegar este login al VPS hay que añadir en la Application Auth0:

- Allowed Callback URLs: `https://marketing.powerupsecosistem.online`
- Allowed Logout URLs: `https://marketing.powerupsecosistem.online`
- Allowed Web Origins: `https://marketing.powerupsecosistem.online`

y rebuild del frontend con `VITE_AUTH0_*`.
