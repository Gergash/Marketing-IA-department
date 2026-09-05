# TikTok Developers — App Review y dominio

Departamento en `https://marketing.powerupsecosistem.online`.  
Estado: **app en evaluación** por TikTok (Login Kit + Content Posting solicitados).

**Hoy en código:** generación de piezas TikTok (9:16), legales y verify `.txt`. **Publicación automática:** fase 2 tras aprobación + implementación OAuth.

---

## 1. App Information (Basic)

| Campo | Valor recomendado |
|-------|-------------------|
| App name | `Business_marketing_depa_IA` |
| Category | Business / Marketing / Productivity |
| Platforms | **Web** |
| Description (≤120 chars, EN) | `AI marketing department: create, review and publish branded social content for business accounts.` |
| Terms of Service URL | `https://marketing.powerupsecosistem.online/terminos` |
| Privacy Policy URL | `https://marketing.powerupsecosistem.online/privacidad` |
| Website URL | `https://marketing.powerupsecosistem.online` |

App icon: 1024×1024 PNG/JPG.

### Consistencia de icono (rechazo típico de review)

TikTok exige el **mismo** icono en:
1. TikTok Developers → Basic Info → App icon
2. Sitio web (hero / logo visible)
3. Favicon de la pestaña del navegador

Asset canónico en el repo (usar el mismo archivo al resubmit):

| Uso | Archivo |
|-----|---------|
| Subir a TikTok (1024) | `frontend/public/app-icon-1024.jpg` |
| Sitio / OG | `frontend/public/logo-marketing-agentico.jpg` o `app-icon-512.png` |
| Favicon | `frontend/public/favicon.ico` (+ `favicon-32.png`) |
| Apple touch | `frontend/public/apple-touch-icon.png` |

Tras deploy, verificar:

```bash
curl -sI https://marketing.powerupsecosistem.online/favicon.ico
curl -sI https://marketing.powerupsecosistem.online/app-icon-512.png
# Abrir la landing: el logo del robot "auto" debe verse igual que el App icon de TikTok
```

No uses un icono genérico distinto en el portal de TikTok.

---

## 2. Verificación de dominio (URL properties)

TikTok pide un archivo en la **raíz** del dominio:

`https://marketing.powerupsecosistem.online/tiktokXXXX.txt`

En `.env.production` (VPS):

```env
TIKTOK_VERIFY_FILENAME=tiktokXXXX.txt
TIKTOK_VERIFY_CONTENT=tiktokXXXX
```

Reiniciar API y comprobar:

```bash
curl -s https://marketing.powerupsecosistem.online/tiktokXXXX.txt
```

Caddy debe enrutar `tiktok*.txt` → API (`Caddyfile.marketing.snippet`).

Alternativa: archivo en `static/tiktok-verify/` con el nombre exacto del portal.

---

## 3. Texto para App Review — productos y scopes

Pegar en *Explain how each product and scope works* (inglés):

```
Marketing DEPA IA (https://marketing.powerupsecosistem.online) is an internal web app for our marketing team to create, review, and publish branded content with AI assistance.

Login Kit: Authorized team members connect their TikTok account via OAuth. We store access tokens securely per tenant and show connected accounts in Integrations. Users can disconnect anytime.

Content Posting API: After human approval (human-in-the-loop), we publish the approved vertical video or image+caption to the connected TikTok account. Flow: brief → AI strategy/copy/design (9:16) → quality review → manual approval → publish. We never auto-post without approval.

Scopes:
• user.info.basic — Display connected account in our UI for account selection.
• video.upload / video.publish — Upload approved media from our server and publish to the authenticated user's profile.

Terms: https://marketing.powerupsecosistem.online/terminos
Privacy: https://marketing.powerupsecosistem.online/privacidad
```

---

## 4. Tras aprobación TikTok (fase 2 — desarrollo)

Pendiente en código:

- OAuth Login Kit → `/api/auth/login/tiktok`, `/api/auth/callback/tiktok`
- Botón **Conectar TikTok** en Integraciones
- `_publish_run` para `red_social=tiktok`
- Redirect URI en portal: `https://marketing.powerupsecosistem.online/api/auth/callback/tiktok`

Mientras tanto: generar piezas en el dashboard y publicar manualmente en TikTok si hace falta.

---

## 5. Checklist

- [ ] Terms + Privacy en portal (URLs prod, no Google Slides)
- [ ] Dominio verificado (`.txt` 200)
- [ ] App enviada a review
- [ ] ⏳ Esperar aprobación
- [ ] Implementar OAuth + publish (post-aprobación)

---

Ver también: [`proceso-integracion-redes.md`](proceso-integracion-redes.md) · [`static/tiktok-verify/README.md`](../../static/tiktok-verify/README.md)
