# Meta / Instagram OAuth — URLs de producción

> **2026-09-17 noche:** el usuario pidió documentar el repo y **no** pasar la app de Meta a Live hasta dar la bandera. Este archivo es la guía; **no ejecutar** el trámite App Review / Live hasta esa bandera.

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
- `instagram_manage_messages` · `pages_messaging` · `pages_manage_metadata` (agente de DMs, ver §7)

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
| DMs no llegan a la bandeja | Webhook sin verificar, campo `messages` no suscrito o cuenta conectada antes de los permisos de mensajería (reconectar) |
| La bandeja recibe pero el agente no responde | Interruptor del agente apagado en la cuenta, conversación pausada / `requiere_humano`, o worker Celery caído |

---

## 7. Agente de DMs (Instagram + Messenger)

El agente responde DMs con tono humano, pide nombre, teléfono/WhatsApp y ciudad/barrio (uno a la vez),
registra el motivo y deja todo en **Estudio → Bandeja de DMs**. Si el tema lo requiere (quejas, pagos,
pide hablar con alguien) marca `requiere_humano` y deja de responder. Si el LLM falla **no** envía
plantillas: la conversación pasa a humano. Si le preguntan, dice con honestidad que es el asistente virtual.

### 7.1 Portal Meta Developers

1. App → **Webhooks** (o *Messenger* / *Instagram* → *Webhooks*):
   - **Callback URL:** `https://marketing.powerupsecosistem.online/api/webhooks/meta`
   - **Verify token:** el mismo valor de `META_WEBHOOK_VERIFY_TOKEN` en `.env.production`
   - Suscribir el campo **`messages`** en los objetos **Page** e **Instagram**.
2. Añadir los permisos `instagram_manage_messages`, `pages_messaging`, `pages_manage_metadata`.
3. Instagram → la cuenta profesional debe tener activado **Permitir acceso a mensajes** (Configuración → Privacidad → Mensajes → Herramientas conectadas).

### 7.2 Estudio

1. **Reconectar Meta** en Integraciones (las cuentas conectadas antes no tienen los permisos de mensajería).
   Al conectar, el gateway suscribe cada Fan Page a `messages` (`POST /{page_id}/subscribed_apps`).
2. En **Bandeja de DMs**, activar el interruptor **Agente** en cada cuenta (apagado por defecto).
   Activarlo vuelve a intentar la suscripción de la página.

### 7.3 Modo Development vs Live

En **Development** solo funcionan DMs de personas con rol en la app (admins / testers). Para el público
general hace falta **App Review** de los permisos de mensajería y pasar la app a **Live**.
**No pasar a Live hasta que el usuario dé la bandera** (ver nota al inicio).

### 7.4 Reglas de envío

- Ventana de 24 h de Meta: el agente responde siempre dentro de la ventana (contesta a un mensaje entrante);
  la respuesta manual desde la bandeja se bloquea si pasaron más de 24 h desde el último mensaje de la persona.
- `DM_DEBOUNCE_SECONDS` agrupa mensajes seguidos en una sola respuesta; `DM_AGENT_REPLY_DELAY_SECONDS`
  controla la pausa "escribiendo…" (tope 4 s).
- Responder a mano desde la bandeja **pausa** al agente en esa conversación; *Reanudar agente* lo reactiva.
- `DM_AGENT_DRY_RUN` debe quedar en `false` (o sin definir) en `.env.production`: con `true` el agente no envía nada a Meta.

### 7.5 Bandeja de DMs (estudio)

- Chips de estado con luz parpadeante de su color: **Nuevo** (azul), **En conversación** (ámbar), **Datos completos** (verde), **Requiere humano** (rojo), **Cerrado** (gris). Con conversaciones en ese estado la luz late más rápido; clic filtra la tabla.
- Filtros por cuenta y motivo, búsqueda (nombre, teléfono, ciudad, motivo), **Exportar CSV** (abre bien en Excel).
- Al abrir un contacto: datos, motivo, resumen, conversación en burbujas (persona / agente / equipo), pausar/reanudar, cambiar estado, notas internas y respuesta manual.

### 7.6 Probar antes de producción

En staging local con DMs simulados (`DM_AGENT_DRY_RUN=true` + `scripts/simulate_dm.py`) o reales vía túnel:
[`docs/staging-e2e.md`](../../docs/staging-e2e.md#agente-de-dms-en-staging-local).

---

Ver también: [`proceso-integracion-redes.md`](proceso-integracion-redes.md) · [`vps-hostinger.md`](vps-hostinger.md)
