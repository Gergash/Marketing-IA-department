# Panel de administrador

Dashboard de control de la plataforma SaaS: usuarios, créditos, pagos Bold y consumo de proveedores (Venice/fal/…).

**Auth0:** este panel no depende del IdP. Trabaja con `tenant_id` + `AppUser`. Cuando Auth0 entre, solo cambia cómo se valida el JWT; el panel sigue igual. El botón «Restablecer contraseña» hoy genera una clave local temporal; con Auth0 debería enlazar al dashboard del IdP.

## Activar

```env
STAGING_SAAS_ENABLED=true
ADMIN_PANEL_ENABLED=true
ADMIN_EMAILS=tu@email.com          # bootstrap: admin aunque is_admin=false en BD
JWT_SECRET=<secreto-largo>
```

Frontend: `VITE_STAGING_SAAS=true` (bake-time). Ruta: `/admin` (requiere sesión).

## Capacidades

| Pestaña | Qué hace |
|---------|----------|
| Resumen | KPIs usuarios/créditos/ingresos + mix de proveedores |
| Usuarios | Buscar, detalle, activar/desactivar, promover admin, ajustar créditos, reset password |
| Pagos | Listado Bold (paid/pending/failed) |
| Consumo | Uso por proveedor o por usuario (7/30/90 días) |

**Nunca** se expone `password_hash`. Solo `password_algo` (p.ej. `pbkdf2_sha256`).

## API

Prefijo `/api/admin/*` — requiere JWT de un admin (`is_admin` o `ADMIN_EMAILS`):

- `GET /overview`
- `GET /users`, `GET /users/{id}`, `PATCH /users/{id}`
- `POST /users/{id}/reset-password`
- `POST /users/{id}/credits`
- `GET /payments`
- `GET /usage?group_by=provider|user&days=30`

`GET /api/auth/me` incluye `is_admin` para mostrar el enlace en la UI.

## Bootstrap del primer admin

1. Regístrate con el email listado en `ADMIN_EMAILS`, **o**
2. En BD: `UPDATE app_users SET is_admin = true WHERE email = '…';`
