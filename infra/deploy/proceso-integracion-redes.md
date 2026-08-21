# Proceso de integración en producción — Marketing DEPA IA

Documento vivo del despliegue en **VPS Hostinger KVM 4** (coexistencia con **InsightFlow**) y conexión de redes sociales.

**Dominio producción:** `https://marketing.powerupsecosistem.online`  
**VPS:** `insightflow@2.25.107.229` · ruta app `~/apps/marketing-depa-ia`  
**InsightFlow (no tocar):** `https://api.powerupsecosistem.online`

Guía de despliegue base: [`vps-hostinger.md`](vps-hostinger.md)

---

## Estado del proceso (actualizado)

| Fase | Estado | Notas |
|------|--------|-------|
| DNS + Caddy host + Docker compose | ✅ Hecho | Loopback `8000`/`8081`, sin Caddy en compose |
| Dashboard + API en HTTPS | ✅ Hecho | `/api/health`, SPA en `/` |
| Legales (`/terminos`, `/privacidad`) | ✅ Hecho | Servidos por FastAPI (TikTok + Meta) |
| LLM cloud (OpenRouter) | 🔄 En curso | `LLM_PROVIDER=openai` + `OPENAI_API_BASE=https://openrouter.ai/api/v1` |
| Meta / Instagram OAuth | 🔄 En curso | Portal migrado de ngrok → dominio prod; Conectar Meta pendiente de prueba |
| LinkedIn OAuth | ⬜ Pendiente portal | Redirect `…/api/auth/callback/linkedin` |
| **X OAuth + publish** | 🔄 En curso | Código listo; configurar portal + `.env` + Conectar X |
| **TikTok App Review** | ⏳ En evaluación | App enviada; Login Kit + Content Posting pendientes de aprobación |
| TikTok publish (código) | ⬜ Fase 2 | Tras aprobación: implementar OAuth + Content Posting API |

Leyenda: ✅ listo · 🔄 en progreso · ⏳ esperando terceros · ⬜ pendiente

---

## Orden de trabajo acordado

```text
1. Producción VPS (InsightFlow + Marketing coexistiendo)
2. Dominio fijo → reemplazar ngrok en portales y .env.production
3. Meta Developers (Basic + OAuth redirect) → Conectar IG/FB
4. X Developer Portal → Conectar X → post de prueba
5. TikTok Developers (App info + verify + review) — en paralelo
6. Tras aprobación TikTok → OAuth + publish en código
```

---

## URLs canónicas (pegar en portales)

Sustituye solo si cambia el subdominio.

| Uso | URL |
|-----|-----|
| Website / App URL | `https://marketing.powerupsecosistem.online` |
| Terms of Service | `https://marketing.powerupsecosistem.online/terminos` |
| Privacy Policy | `https://marketing.powerupsecosistem.online/privacidad` |
| Meta OAuth callback | `https://marketing.powerupsecosistem.online/api/auth/callback/meta` |
| LinkedIn OAuth callback | `https://marketing.powerupsecosistem.online/api/auth/callback/linkedin` |
| Google OAuth callback | `https://marketing.powerupsecosistem.online/api/auth/callback/google` |
| X OAuth callback | `https://marketing.powerupsecosistem.online/api/auth/callback/x` |
| TikTok verify `.txt` | `https://marketing.powerupsecosistem.online/<tiktokXXXX>.txt` |

**Eliminar** de todos los portales las URIs antiguas de `*.ngrok-free.dev`.

---

## Guías por red

| Red | Documento | Publicación automática hoy |
|-----|-----------|----------------------------|
| Meta / IG / FB | [`meta-oauth-production.md`](meta-oauth-production.md) | ✅ OAuth + Go sidecar |
| LinkedIn | [`vps-hostinger.md`](vps-hostinger.md) § Fase 7 | ✅ Nativo Python (imagen) |
| X | [`x-oauth-production.md`](x-oauth-production.md) | ✅ Nativo Python (tweet + imagen) |
| TikTok | [`tiktok-app-review.md`](tiktok-app-review.md) | ⏳ Solo generación; publish post-review |

---

## Variables `.env.production` (VPS)

Plantilla: [`.env.production.example`](../../.env.production.example)

| Grupo | Variables clave |
|-------|-----------------|
| Dominio | `DOMAIN`, `OAUTH_SUCCESS_REDIRECT_URL`, `PUBLIC_IMAGE_BASE_URL`, `CORS_ORIGINS` |
| LLM | `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_MODEL` |
| Meta | `META_CLIENT_ID`, `META_CLIENT_SECRET`, `META_REDIRECT_URI` |
| X | `X_API_KEY`, `X_API_SECRET`, `X_REDIRECT_URI` |
| TikTok verify | `TIKTOK_VERIFY_FILENAME`, `TIKTOK_VERIFY_CONTENT` |

El compose [`docker-compose.prod.yml`](../docker-compose.prod.yml) **sobrescribe** callbacks y `PUBLIC_IMAGE_BASE_URL` desde `DOMAIN`; aun así `.env.production` no debe contener ngrok (workers leen el archivo).

Tras cambiar secretos:

```bash
cd ~/apps/marketing-depa-ia
docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d api worker video-worker
```

---

## Dashboard — conectar cuentas

1. Abrir `https://marketing.powerupsecosistem.online`
2. **Integraciones** → Conectar Meta / LinkedIn / X
3. En el brief: elegir **Red social** + **Cuenta destino**
4. Ejecutar pipeline → **Aprobar** → publicación

---

## Verificación rápida

```bash
curl -sI https://marketing.powerupsecosistem.online/api/health
curl -sI https://marketing.powerupsecosistem.online/terminos
curl -sI https://api.powerupsecosistem.online/health   # InsightFlow intacto
```

---

## Dev local vs producción

| Entorno | Dominio | OAuth / Meta |
|---------|---------|----------------|
| **Local (Windows)** | `localhost:5173` + `localhost:8000` | ngrok opcional; ver [`arranque-stack.md`](../arranque-stack.md) |
| **Producción (VPS)** | `marketing.powerupsecosistem.online` | Solo dominio prod en portales; **no** ngrok |

---

## Próximos pasos inmediatos

- [ ] Confirmar **Conectar Meta** tras actualizar Meta Developers Basic + redirect
- [ ] Completar **X** en portal + `.env.production` + post de prueba
- [ ] Esperar **TikTok App Review**; luego implementar OAuth/publish
- [ ] OpenRouter: key en prod + validar que agentes no caen a stub
- [ ] Snapshot VPS en Hostinger tras integraciones estables
