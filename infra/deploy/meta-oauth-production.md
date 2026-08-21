# Meta / Instagram OAuth — URLs de producción

Usar cuando el departamento corre en **`https://marketing.powerupsecosistem.online`** (VPS), no ngrok.

App ID del proyecto: `1258515492788752` (mismo valor en `META_APP_ID` / `META_CLIENT_ID`).

---

## 1. Meta for Developers (developers.facebook.com)

App → **App settings** → **Basic**:

| Campo | Valor |
|-------|--------|
| **App domains** | `marketing.powerupsecosistem.online` |
| **Privacy Policy URL** | `https://marketing.powerupsecosistem.online/privacidad` |
| **Terms of Service URL** | `https://marketing.powerupsecosistem.online/terminos` |
| **Site URL** (si aparece) | `https://marketing.powerupsecosistem.online` |

App → **Use cases** / **Facebook Login for Business** → **Settings** (o **Facebook Login** → Settings):

| Campo | Valor |
|-------|--------|
| **Valid OAuth Redirect URIs** | `https://marketing.powerupsecosistem.online/api/auth/callback/meta` |

Importante:

- La URI debe ser **exacta** (https, sin barra final, path completo).
- **Elimina** URIs antiguas de ngrok (`*.ngrok-free.dev`) para evitar confusiones.
- Puedes dejar `http://localhost:8000/api/auth/callback/meta` solo si sigues probando en local.

App → **Use cases** → permisos típicos para IG/Facebook:

- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_posts`
- `instagram_basic`
- `instagram_content_publish`

---

## 2. Variables en `.env.production` (VPS)

Deben coincidir con el portal (Compose también las sobrescribe desde `DOMAIN`):

```env
DOMAIN=marketing.powerupsecosistem.online

OAUTH_SUCCESS_REDIRECT_URL=https://marketing.powerupsecosistem.online/
PUBLIC_IMAGE_BASE_URL=https://marketing.powerupsecosistem.online
META_REDIRECT_URI=https://marketing.powerupsecosistem.online/api/auth/callback/meta

META_CLIENT_ID=1258515492788752
META_CLIENT_SECRET=...
META_APP_ID=1258515492788752
META_APP_SECRET=...
```

Tras editar:

```bash
cd ~/apps/marketing-depa-ia
docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d api worker video-worker
```

---

## 3. Comprobar antes de “Conectar Meta”

```bash
# Health
curl -sI https://marketing.powerupsecosistem.online/api/health

# El login OAuth debe redirigir a facebook.com (desde navegador con sesión + API key)
# Integraciones → Conectar Meta abre:
# https://marketing.powerupsecosistem.online/api/auth/login/meta
```

En el popup de Meta, el usuario debe:

1. Iniciar sesión con cuenta que administra la Fan Page.
2. Seleccionar la(s) página(s) con Instagram Business vinculado.
3. Aceptar permisos.

Tras el callback, el dashboard vuelve a `https://marketing.powerupsecosistem.online/?oauth=success&provider=meta`.

---

## 4. Meta Business Suite (cuenta de negocio)

No sustituye la OAuth Redirect URI de Developers, pero conviene:

- Tener la **Fan Page** vinculada a **Instagram profesional** en Business Suite.
- El usuario que conecta debe ser admin de esa página.
- Si la app está en **Development**, solo cuentas **Test users** / admins de la app pueden autorizar (añádelos en App roles → Test users o usa modo Live tras App Review).

Fan Page ID en `.env` (referencia): `META_FACEBOOK_PAGE_ID=1073015845905959`.

---

## 5. Migración desde ngrok — checklist

- [ ] Meta Developers: redirect URI → dominio producción (quitar ngrok)
- [ ] `.env.production` en VPS sin URLs ngrok
- [ ] Reiniciar contenedores `api` + workers
- [ ] Dashboard → Integraciones → **Conectar Meta**
- [ ] Ver cuenta IG en selector “Cuenta destino”
- [ ] Run de prueba → aprobar → publicar en IG

---

## 6. Errores frecuentes

| Síntoma | Causa |
|---------|--------|
| “Redirect URI mismatch” | URI en portal ≠ `META_REDIRECT_URI` |
| Popup Meta OK pero vuelve con error | `OAUTH_SUCCESS_REDIRECT_URL` incorrecto |
| No aparece IG en cuentas | Página sin IG Business o permisos no concedidos |
| Publicación falla en imagen | `PUBLIC_IMAGE_BASE_URL` debe ser HTTPS producción |

---

Ver también: [`proceso-integracion-redes.md`](proceso-integracion-redes.md) · [`vps-hostinger.md`](vps-hostinger.md)
