# MCP Connect Go (mcp-golang)

MCP server (stdio) for heavy integrations.

## Tools
- `health_status`: heartbeat and host info.
- `publish_social_stub`: placeholder to route heavy social integrations to Go.

## Run
```bash
cd microservices/mcp-connect-go
go mod tidy
go run ./cmd/server
```

This is the gradual connectivity layer. Python can communicate through an MCP client or sidecar bridge.
