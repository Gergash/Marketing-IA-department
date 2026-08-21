# Despliegue en producción — Marketing DEPA IA (coexistencia con InsightFlow)

Guía para subir el backend y el dashboard a la VPS Hostinger KVM 4 **sin tocar** el stack residente InsightFlow.

**Arquitectura:** un solo Caddy en el host gestiona HTTPS de ambos dominios. Marketing DEPA IA publica API/frontend solo en `127.0.0.1`; Postgres, Redis y el Go publisher quedan en la red Docker interna.

| Proyecto | Ruta en VPS | Dominio ejemplo | Compose name |
|----------|-------------|-----------------|--------------|
| InsightFlow | `~/apps/insightflow` | `api.powerupsecosistem.online` | (existente) |
| Marketing DEPA IA | `~/apps/marketing-depa-ia` | `marketing.powerupsecosistem.online` | `marketing-depa-prod` |

---

## Camino rápido

1. Confirmar DNS A → `2.25.107.229` y SSH como `insightflow`.
2. Clonar en `~/apps/marketing-depa-ia` (nunca dentro de `insightflow`).
3. Completar `.env.production` (`DOMAIN`, secretos, LLM cloud).
4. Añadir el bloque de [`Caddyfile.marketing.snippet`](Caddyfile.marketing.snippet) a `/etc/caddy/Caddyfile` → `reload`.
5. `docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d --build`
6. Verificar health de **ambos** dominios y actualizar OAuth en Meta/LinkedIn/X/TikTok.

Detalle abajo. Archivo de compose: [`../docker-compose.prod.yml`](../docker-compose.prod.yml).

**Proceso vivo (estado Meta / X / TikTok / OpenRouter):** [`proceso-integracion-redes.md`](proceso-integracion-redes.md)

---

## Reglas de oro

| Sí | No |
|----|----|
| Usuario SSH `insightflow@2.25.107.229` | Usar `root` para el día a día |
| Caddy del host (`/etc/caddy/Caddyfile`) | Levantar otro Caddy en el compose de Marketing |
| Puertos `127.0.0.1:8000` y `127.0.0.1:8081` | Bindear `80`/`443` desde este compose |
| Postgres/Redis/`8088` solo `expose` / red Docker | Publicar DB o Go publisher a Internet |
| Snapshot Hostinger tras go-live | Modificar o parar `~/apps/insightflow` |

---

## Fase 0 — Antes del SSH

- [ ] Llave `ed25519` autorizada en `insightflow@2.25.107.229`
- [ ] Dominio/subdominio con **DNS A → `2.25.107.229`** (ej. `marketing.powerupsecosistem.online`)
- [ ] Secretos listos: `POSTGRES_PASSWORD` (distinto al de InsightFlow), `API_KEY`, OpenAI/Anthropic, fal, Shotstack, OAuth Meta/LinkedIn/X, TikTok verify
- [ ] Leída esta guía y el snippet de Caddy

---

## Fase 1 — Línea base (InsightFlow intacto)

```bash
ssh insightflow@2.25.107.229

docker ps
sudo ufw status
# ufw debe permitir 22, 80, 443

curl -sI https://api.powerupsecosistem.online/health
# Esperado: 200 OK
```

Si InsightFlow no responde, **no continúes** el despliegue de Marketing.

Comprobar que los loopback previstos están libres:

```bash
ss -tlnp | grep -E ':8000|:8081' || echo "8000/8081 libres en loopback"
```

Si `8000` u `8081` ya están ocupados, elige otros (ej. `18000` / `18081`), actualiza el compose **y** el bloque Caddy antes del `up`.

---

## Fase 2 — Clonar en aislamiento

```bash
mkdir -p ~/apps/marketing-depa-ia
cd ~/apps/marketing-depa-ia
git clone <URL_REPO_MARKETING> .
```

El compose usa `name: marketing-depa-prod` → contenedores y volúmenes no colisionan con InsightFlow/Malcom.

---

## Fase 3 — Compose de coexistencia

`infra/docker-compose.prod.yml` ya está preparado para esta VPS:

- **Sin** servicio `caddy`
- `api` → `127.0.0.1:8000:8000`
- `frontend` → `127.0.0.1:8081:80`
- Postgres, Redis, `go-publisher` **sin** `ports:` al host (`go-publisher` solo `expose: 8088`)

No reintroduzcas un Caddy en el compose ni bindees `80`/`443`.

---

## Fase 4 — Variables de entorno

```bash
cd ~/apps/marketing-depa-ia
cp .env.production.example .env.production
nano .env.production
```

| Variable | Valor |
|----------|--------|
| `DOMAIN` | Hostname sin `https://` (ej. `marketing.powerupsecosistem.online`) |
| `POSTGRES_PASSWORD` | Fuerte y **distinto** al de InsightFlow |
| `API_KEY` | Obligatorio en prod (dashboard) |
| `CORS_ORIGINS` | `https://marketing.powerupsecosistem.online` |
| `LLM_PROVIDER` | `openai` + OpenRouter (`OPENAI_API_BASE`) o `anthropic` — no Ollama en VPS compartida |
| `IMAGE_PROVIDER` / `FAL_API_KEY` | fal.ai |
| `VIDEO_PROVIDER` / `SHOTSTACK_*` | Shotstack |
| OAuth secrets | Meta, LinkedIn, Google, X |

Compose sobrescribe callbacks a:

`https://${DOMAIN}/api/auth/callback/{meta|linkedin|google|x}`

y `PUBLIC_IMAGE_BASE_URL=https://${DOMAIN}` (sustituye ngrok).

---

## Fase 5 — Caddy del host

```bash
sudo nano /etc/caddy/Caddyfile
```

Añade el bloque de [`Caddyfile.marketing.snippet`](Caddyfile.marketing.snippet) (o equivalente). Resumen:

```caddyfile
marketing.powerupsecosistem.online {
	encode gzip

	@backend path /api* /static* /docs* /openapi.json /terminos* /privacidad* /terms* /privacy* /tiktok*.txt
	handle @backend {
		reverse_proxy 127.0.0.1:8000
	}

	handle {
		reverse_proxy 127.0.0.1:8081
	}
}
```

Validar y recargar **sin** tumbar InsightFlow:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

---

## Fase 6 — Levantar contenedores

```bash
cd ~/apps/marketing-depa-ia
docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d --build

docker compose -f infra/docker-compose.prod.yml ps
docker compose -f infra/docker-compose.prod.yml --env-file .env.production logs -f api
```

Verificación:

```bash
curl -sI http://127.0.0.1:8000/api/health
curl -sI https://marketing.powerupsecosistem.online/api/health
curl -sI https://marketing.powerupsecosistem.online/terminos
curl -sI https://marketing.powerupsecosistem.online/privacidad

# InsightFlow sigue vivo
curl -sI https://api.powerupsecosistem.online/health
```

---

## Fase 7 — Portales OAuth y redes (efecto dominó)

Sustituye `DOMAIN` por el hostname real.

| Proveedor | Qué actualizar | Guía |
|-----------|----------------|------|
| **Meta** | Redirect URI `https://DOMAIN/api/auth/callback/meta`; Basic Settings (dominio, privacy, terms) | [`meta-oauth-production.md`](meta-oauth-production.md) |
| **LinkedIn** | `https://DOMAIN/api/auth/callback/linkedin` | Fase 7 arriba |
| **Google** | `https://DOMAIN/api/auth/callback/google` | Fase 7 arriba |
| **X** | Callback `https://DOMAIN/api/auth/callback/x`; Read and write; keys en `.env.production` | [`x-oauth-production.md`](x-oauth-production.md) |
| **TikTok** | Terms, Privacy, verify `.txt`, App Review (Login Kit + Content Posting) | [`tiktok-app-review.md`](tiktok-app-review.md) |

**Alcance actual:** publicación nativa **Meta / LinkedIn / X**. TikTok: legales + verify + app **en evaluación**; OAuth/publish en código tras aprobación.

**Migración ngrok → prod:** quitar URIs `*.ngrok-free.dev` de todos los portales; en VPS `.env.production` usar solo `marketing.powerupsecosistem.online` y reiniciar `api` + `worker` + `video-worker`.

---

## Fase 8 — Checklist de operación segura

- [ ] `https://api.powerupsecosistem.online/health` → 200 (InsightFlow)
- [ ] Dashboard Marketing carga en `https://marketing.powerupsecosistem.online/`
- [ ] `https://…/api/health`, `/terminos`, `/privacidad` → 200
- [ ] `ss -tlnp | grep -E ':80|:443|:8000|:8081'` — 80/443 = Caddy host; 8000/8081 = `127.0.0.1` solamente
- [ ] Postgres / Redis / `8088` **no** escuchan en `0.0.0.0`
- [ ] `docker ps` muestra ambos stacks
- [ ] Snapshot VPS en Hostinger
- [ ] Volúmenes Docker de Marketing documentados como independientes de InsightFlow

---

## Operación diaria

```bash
cd ~/apps/marketing-depa-ia

# Logs
docker compose -f infra/docker-compose.prod.yml --env-file .env.production logs -f api worker

# Actualizar código
git pull
docker compose -f infra/docker-compose.prod.yml --env-file .env.production up -d --build

# No tocar
# ~/apps/insightflow
```

---

## Referencias en el repo

| Archivo | Rol |
|---------|-----|
| [`proceso-integracion-redes.md`](proceso-integracion-redes.md) | **Estado del proceso** y orden de trabajo |
| [`meta-oauth-production.md`](meta-oauth-production.md) | Meta / Instagram OAuth en prod |
| [`x-oauth-production.md`](x-oauth-production.md) | X OAuth + publicación |
| [`tiktok-app-review.md`](tiktok-app-review.md) | TikTok App Review + verify |
| [`../docker-compose.prod.yml`](../docker-compose.prod.yml) | Servicios prod (sin Caddy) |
| [`Caddyfile.marketing.snippet`](Caddyfile.marketing.snippet) | Bloque para `/etc/caddy/Caddyfile` |
| [`../../.env.production.example`](../../.env.production.example) | Plantilla de secretos |
| [`../arranque-stack.md`](../arranque-stack.md) | Arranque **local** (dev Windows), no prod |

---

## Siguiente paso

Seguir [`proceso-integracion-redes.md`](proceso-integracion-redes.md): Conectar Meta y X en el dashboard, post de prueba, y esperar TikTok App Review antes de implementar publish nativo TikTok.
