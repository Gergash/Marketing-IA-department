# Staging local — Marketing DEPA IA

Landing, registro/login por correo (único), botón Bold y créditos para publicar en redes.

## Activar en local

### 1. Backend

Copia variables de `.env.staging.example` a `.env` en la raíz del proyecto:

```bash
STAGING_SAAS_ENABLED=true
JWT_SECRET=un-secreto-largo-aleatorio
BOLD_API_KEY=<llave identidad Bold>
BOLD_INTEGRITY_SECRET=<llave secreta Bold>
BOLD_WEBHOOK_SECRET=<misma llave secreta>
PACK_AMOUNT_COP=99000
CREDITS_PER_PACK=100
STAGING_SUCCESS_REDIRECT_URL=http://localhost:5173/app?paid=1
```

Instala dependencia nueva:

```bash
pip install PyJWT
```

Arranca API y frontend como siempre (`uvicorn` + `npm run dev` en `frontend/`).

SQLite crea tablas `app_users`, `credit_wallets` y `payment_records` al iniciar (schema_patches).

### 2. Frontend

Crea `frontend/.env.local`:

```bash
VITE_STAGING_SAAS=true
```

### 3. Rutas

| URL | Pantalla |
|-----|----------|
| `/` | Landing del departamento de marketing agéntico |
| `/login` | Registro o login (email único) |
| `/app` | Estudio de marketing (dashboard existente) |

Tras **registro exitoso** (correo no repetido) o login, se muestra el **botón Bold** para comprar el paquete de créditos.

## Bold + webhook en dev

1. Panel Bold → Webhook: `https://<tu-ngrok>/api/billing/bold-webhook`
2. `BOLD_WEBHOOK_SECRET` = misma llave secreta del botón (patrón Malcom/InsightFlow).
3. Referencia de orden: `MDIA-{tenant_id}-{timestamp}` — el webhook extrae `tenant_id` y acredita `CREDITS_PER_PACK`.

Para probar pagos reales necesitas ngrok apuntando al gateway `:8000`.

## Créditos por publicación

| Tipo | Créditos |
|------|----------|
| Imagen estática | 1 |
| Imagen IA o diseño sobre foto del usuario | 2 |
| Video con subtítulos | 5 |
| Reel / clip IA | 8 |

Si no hay créditos suficientes al publicar, la API responde **402 Payment Required**.

## Endpoints nuevos

- `POST /api/auth/register` — email, password, full_name
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/billing/credits`
- `GET /api/billing/bold-checkout` — firma integridad Bold (requiere JWT)
- `POST /api/billing/bold-webhook`

## Producción

Mantén `STAGING_SAAS_ENABLED=false` en producción hasta validar el flujo completo. El modo legacy con `API_KEY` sigue funcionando cuando staging está desactivado.
