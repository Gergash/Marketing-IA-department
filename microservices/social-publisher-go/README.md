# Social Publisher Go (MCP-ready boundary)

Microservicio sidecar para publicar en redes. **Stateless por request**: el gateway
resuelve la cuenta destino (`oauth_tokens` multi-cuenta) y envía el token + account_id
ya elegidos. No busca tokens en DB.

## Endpoints

- `GET /health`
- `POST /publish`

### Payload `POST /publish`

```json
{
  "platform": "instagram",
  "copy": "...",
  "image_url": "https://...",
  "video_url": "https://...",
  "content_format": "feed|story|reel|user_clip_reel",
  "access_token": "<token de la cuenta destino>",
  "account_id": "<IG Business ID>",
  "idempotency_key": ""
}
```

Plataformas: **solo Instagram/Facebook** (Meta Graph). LinkedIn se publica nativamente desde el gateway Python (`agents/marketing_agents/social_providers.py`, API versionada `/rest/images` + `/rest/posts`); mandar `platform=linkedin` aquí devuelve 400. TikTok = fase 2 (documentado en `estado-actual.txt`; requiere Login Kit + auditoría de app).

Actualizado con el modelo multi-cuenta (2026-07) y formatos `reel` / `user_clip_reel`.

## Run

```bash
go run ./cmd/server
```

Escucha en `:8088`. Se integra desde `gateway/app/services/pipeline_service.py`
(`_publish_via_go` / `_resolve_publish_token`).
