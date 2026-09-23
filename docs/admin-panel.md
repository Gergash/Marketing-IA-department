# Panel de administrador

Dashboard SaaS en `/admin`: usuarios, créditos, pagos Bold y consumo de proveedores de imagen/video (Venice, fal, gpt-image-2 vía Venice, Shotstack, etc.).

**Idea clave:** Auth0 solo autentica. El panel lee **tablas propias** (`app_users`, `payment_records`, `api_usage_events`, `credit_wallets`). No consulta la API de Management de Auth0 ni el dashboard de Venice/fal.

## Quick path

1. Backend: `STAGING_SAAS_ENABLED=true`, `ADMIN_PANEL_ENABLED=true`, `ADMIN_EMAILS=info@tuempresa.com`
2. Frontend: `VITE_STAGING_SAAS=true` + Auth0 (`VITE_AUTH0_*`)
3. Login Auth0 con el email de `ADMIN_EMAILS` → `http://localhost:5173/admin`

## Cómo llegan los datos al panel

```text
Auth0 (identidad)          Bold (pago)              Venice / fal / Shotstack (APIs)
        │                       │                              │
        ▼                       ▼                              ▼
  ID token Bearer      webhook /api/billing/*         publish / debit créditos
        │                       │                              │
        ▼                       ▼                              ▼
   upsert AppUser         PaymentRecord              ApiUsageEvent + CreditWallet
   + CreditWallet         status paid|pending|failed   provider = venice|fal|…
        │                       │                              │
        └───────────────────────┴──────────────────────────────┘
                                        │
                                        ▼
                              GET /api/admin/*  →  UI /admin
```

### Usuarios

| Paso | Qué ocurre |
|------|------------|
| 1 | El usuario se registra o inicia sesión en Auth0 Universal Login. |
| 2 | La SPA envía el **ID token** como `Authorization: Bearer`. |
| 3 | El gateway valida JWKS y hace **upsert** de `AppUser` por `auth0_sub` (+ email, `tenant_id`, wallet). |
| 4 | Ese registro aparece en **Usuarios**. Si solo existe en Auth0 y nunca llamó a la API, **no** estará aquí. |

Admin: email en `ADMIN_EMAILS` **o** `is_admin=true` en BD. Contraseñas se gestionan en Auth0; el panel no las muestra (`password_algo` = `auth0`).

### Pagos

| Paso | Qué ocurre |
|------|------------|
| 1 | Usuario autenticado pide checkout Bold (`GET /api/billing/bold-checkout`). |
| 2 | Paga en Bold; Bold notifica `POST /api/billing/bold-webhook`. |
| 3 | Se crea/actualiza `PaymentRecord` (`provider=bold`, `amount_cop`, `credits_added`, `status`). |
| 4 | Si `paid`, se acreditan créditos en `CreditWallet`. |
| 5 | La pestaña **Pagos** lista esos registros; el **Resumen** suma solo `status=paid` (ingresos/créditos vendidos) y cuenta `pending`. |

Sin `BOLD_API_KEY` / secretos, el estudio funciona pero no hay pagos reales → KPIs de ingresos en 0.

### Consumo Venice / fal / gpt-image-2

| Paso | Qué ocurre |
|------|------------|
| 1 | En staging SaaS, al **publicar** (o debitar créditos de imagen/reel) el pipeline llama a `record_usage`. |
| 2 | Se inserta `ApiUsageEvent` con `tenant_id`, `provider`, `operation`, `credits_cost`, `run_id`. |
| 3 | `provider` = el del run o, si no hay, `IMAGE_PROVIDER` del `.env` (`venice`, `fal`, `openai`, `shotstack`, `mock`, …). |
| 4 | gpt-image-2 vía Venice se contabiliza como proveedor **`venice`** (el modelo puede ir en el campo `model` del evento cuando se rellene). |
| 5 | **Consumo** y el bloque «Uso por proveedor» del **Resumen** agregan esos eventos. Se excluye el proveedor sintético `admin` (ajustes manuales de créditos). |

Si nadie ha publicado con staging activo, el mix de proveedores estará vacío aunque Venice esté configurado en `.env`.

## Resumen — qué se muestra

La pestaña **Resumen** llama `GET /api/admin/overview` y pinta:

| KPI en UI | Campo API | Cómo se calcula |
|-----------|-----------|-----------------|
| Usuarios registrados | `users_total` | `COUNT(app_users)` |
| Activos últimos 30 días | `users_active_30d` | Tenants con login, uso API o agent runs en 30 días (unión) |
| Registros últimos 7 días | `users_registered_7d` | `AppUser.created_at` ≥ 7 días |
| Registros últimos 30 días | `users_registered_30d` | Igual, 30 días |
| Créditos vendidos | `credits_sold` | `SUM(payment_records.credits_added)` donde `status=paid` |
| Créditos consumidos | `credits_consumed` | `SUM(api_usage_events.credits_cost)` > 0, sin `provider=admin` |
| Créditos pendientes | `credits_outstanding` | `SUM(credit_wallets.balance)` (saldo aún no gastado) |
| Ingresos totales | `revenue_cop_total` | `SUM(amount_cop)` pagos `paid` |
| Pagos pagados | `payments_paid_count` | Conteos Bold `paid` |
| Pagos pendientes | `payments_pending_count` | Conteos Bold `pending` |
| Uso por proveedor | `usage_by_provider` | Barras: eventos / units / créditos y `%` de volumen por `venice`, `fal`, etc. |

## Otras pestañas

| Pestaña | Fuente | Acciones |
|---------|--------|----------|
| Usuarios | `AppUser` + wallet + métricas | Buscar, activar/desactivar, promover admin, ajustar créditos |
| Pagos | `PaymentRecord` | Filtrar paid / pending / failed |
| Consumo | `ApiUsageEvent` | Agrupar por proveedor o usuario (7 / 30 / 90 días) |

## Activar

```env
STAGING_SAAS_ENABLED=true
ADMIN_PANEL_ENABLED=true
ADMIN_EMAILS=info@powerupsagencia.com
AUTH0_DOMAIN=...
AUTH0_CLIENT_ID=...
```

Frontend: `VITE_STAGING_SAAS=true` + `VITE_AUTH0_*`. Ruta: `/admin`.

## API

Prefijo `/api/admin/*` — JWT de admin (`is_admin` o `ADMIN_EMAILS`):

- `GET /overview`
- `GET /users`, `GET /users/{id}`, `PATCH /users/{id}`
- `POST /users/{id}/reset-password` → **410** (usar Auth0)
- `POST /users/{id}/credits`
- `GET /payments`
- `GET /usage?group_by=provider|user&days=30`

`GET /api/auth/me` incluye `is_admin` para el enlace en la UI.

## Bootstrap del primer admin

1. Pon tu correo en `ADMIN_EMAILS` y reinicia la API.
2. Regístrate / login en Auth0 con **ese mismo** email (vía la app, no abriendo `/u/signup` a mano).
3. Abre `/admin`.

Alternativa en BD: `UPDATE app_users SET is_admin = true WHERE email = '…';`

## Checklist de verificación

- [ ] Tras login Auth0, el email aparece en **Usuarios** (hubo al menos una llamada API).
- [ ] Con Bold configurado y un pago de prueba, el pago sale en **Pagos** y suben ingresos/créditos vendidos en **Resumen**.
- [ ] Tras publicar una imagen/reel en staging, **Consumo** / «Uso por proveedor» muestra `venice` o `fal` (según `IMAGE_PROVIDER`).

## Relacionado

- Identidad Auth0: [`docs/auth0.md`](auth0.md)
- Código: `gateway/app/api/admin.py`, `usage_service.py`, `billing.py`, `frontend/src/AdminPanel.jsx`
