# Social Publisher Go (MCP-ready boundary)

Microservicio inicial para encapsular adaptadores de publicacion social.

## Endpoints

- `GET /health`
- `POST /publish`

## Run

```bash
go run ./cmd/server
```

Este servicio se integra desde `gateway/app/services/pipeline_service.py`.
