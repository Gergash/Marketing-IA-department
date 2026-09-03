# X (Twitter) — OAuth y publicación en producción

App en **developer.x.com** + departamento en `https://marketing.powerupsecosistem.online`.

El código usa **OAuth 1.0a** (3-legged): Consumer Key/Secret en `.env` + token de usuario tras **Conectar X** en Integraciones.

---

## 1. Portal X Developer

**Settings → User authentication settings → Set up / Edit**

| Campo | Valor |
|-------|--------|
| App permissions | **Read and write** |
| Type of App | **Web App** |
| Callback URI / Redirect URL | `https://marketing.powerupsecosistem.online/api/auth/callback/x` |
| Website URL | `https://marketing.powerupsecosistem.online` |

**Keys and tokens:**

| Portal | `.env.production` |
|--------|-------------------|
| API Key (Consumer Key) | `X_API_KEY` |
| API Key Secret (Consumer Secret) | `X_API_SECRET` |
| Bearer Token | `X_BEARER_TOKEN` (opcional; app-only, **no publica**) |
| Access Token + Secret | `X_ACCESS_TOKEN` + `X_ACCESS_TOKEN_SECRET` (opcional; publica sin Conectar X) |
| OAuth 2.0 Client ID / Secret | `X_CLIENT_ID` + `X_CLIENT_SECRET` (User auth settings; no usados aún por publish) |

Quitar callbacks ngrok del portal si quedaron.

URLs legales (si las pide la app):

- Privacy: `https://marketing.powerupsecosistem.online/privacidad`
- Terms: `https://marketing.powerupsecosistem.online/terminos`

---

## 2. `.env.production` (VPS)

```env
X_API_KEY=...
X_API_SECRET=...
X_BEARER_TOKEN=...                    # opcional
X_REDIRECT_URI=https://marketing.powerupsecosistem.online/api/auth/callback/x

DOMAIN=marketing.powerupsecosistem.online
OAUTH_SUCCESS_REDIRECT_URL=https://marketing.powerupsecosistem.online/
PUBLIC_IMAGE_BASE_URL=https://marketing.powerupsecosistem.online
```

Reiniciar API (OAuth vive en el gateway):

```bash
cd ~/apps/marketing-depa-ia
docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d api
```

---

## 3. Conectar cuenta

1. Dashboard → **Integraciones** → **Conectar X**
2. Autorizar con la cuenta que publicará
3. Verificar fila `provider: x`, `@usuario` en la tabla

Flujo técnico: `GET /api/auth/login/x` → Twitter authorize → `GET /api/auth/callback/x` → guarda token en `oauth_tokens` (secret en `refresh_token`).

---

## 4. Publicar

1. Brief: **Red social = X**
2. Formato **feed** (requiere imagen)
3. Elegir cuenta X en **Cuenta destino**
4. Ejecutar → aprobar run

Pipeline: media upload v1.1 + `POST /2/tweets` (OAuth 1.0a user context).

---

## 5. Checklist

- [ ] Portal: Read and write + Web App + callback prod
- [ ] `X_API_KEY` + `X_API_SECRET` en VPS `.env.production`
- [ ] API + workers reiniciados tras cambio de env
- [ ] Conectar X OK **o** tokens en env
- [ ] Post de prueba con URL en `x.com`

---

## 6. Errores frecuentes

| Síntoma | Causa |
|---------|--------|
| `X_API_KEY / X_API_SECRET no configurados` | Faltan keys o API no reiniciada |
| Redirect mismatch | Callback portal ≠ `X_REDIRECT_URI` |
| OAuth OK, publish falla | Run sin imagen o plan API sin write |
| Media upload falla | `PUBLIC_IMAGE_BASE_URL` debe ser HTTPS prod |

---

Ver también: [`proceso-integracion-redes.md`](proceso-integracion-redes.md) · [`vps-hostinger.md`](vps-hostinger.md)
