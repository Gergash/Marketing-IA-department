# Auth0 — Marketing DEPA IA

Única identidad SaaS. El login/registro local (email + JWT propio) fue eliminado.

Verificado en local (17-sep-2026 noche): signup de `info@powerupsagencia.com` desde `/login` → entra al estudio. Snapshot: [`estado-saas-auth0-2026-09-17.md`](estado-saas-auth0-2026-09-17.md).

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
```

## Flujo

1. `/login` → botones Auth0 (`loginWithRedirect`, signup con `screen_hint=signup`)
2. **No** pegar ni refrescar `https://…auth0.com/u/signup` a mano → error `some body keys are invalid`
3. SPA envía el **ID token** (`getIdTokenClaims().__raw`) como `Authorization: Bearer`
4. API valida JWKS RS256, hace upsert de `AppUser` por `auth0_sub` + email, crea `tenant_id` + wallet

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
