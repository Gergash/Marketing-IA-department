// Servidor MCP por stdio (herramientas health_status y publish_social_stub) + HTTP GET de salud en :8090.
package main

import (
    "encoding/json"
    "fmt"
    "log"
    "net/http"
    "os"
    "time"

    mcp "github.com/metoro-io/mcp-golang"
    "github.com/metoro-io/mcp-golang/transport/stdio"
)

type HealthArgs struct {
    Caller string `json:"caller" jsonschema:"description=Service requesting health info"`
}

type PublishArgs struct {
    Platform string `json:"platform" jsonschema:"required,description=Target platform"`
    Copy     string `json:"copy" jsonschema:"required,description=Post copy text"`
    ImageURL string `json:"image_url" jsonschema:"description=Image URL"`
}

// main registra herramientas MCP, lanza el wrapper HTTP en goroutine y bloquea en Serve() por stdio.
func main() {
    // HTTP wrapper for healthchecks and local orchestration probes.
    // Keep MCP tools on stdio while exposing liveness over HTTP.
    go startHTTPWrapper()

    server := mcp.NewServer(stdio.NewStdioServerTransport())

    _ = server.RegisterTool("health_status", "Reports MCP connectivity status", func(a HealthArgs) (*mcp.ToolResponse, error) {
        host, _ := os.Hostname()
        msg := fmt.Sprintf("mcp-go alive host=%s caller=%s ts=%s", host, a.Caller, time.Now().UTC().Format(time.RFC3339))
        return mcp.NewToolResponse(mcp.NewTextContent(msg)), nil
    })

    _ = server.RegisterTool("publish_social_stub", "Stub heavy social integration in Go layer", func(a PublishArgs) (*mcp.ToolResponse, error) {
        payload := fmt.Sprintf("queued platform=%s image=%s chars=%d", a.Platform, a.ImageURL, len(a.Copy))
        return mcp.NewToolResponse(mcp.NewTextContent(payload)), nil
    })

    if err := server.Serve(); err != nil {
        panic(err)
    }
}

// startHTTPWrapper escucha en :8090 y expone JSON de salud para probes sin usar el transporte MCP.
func startHTTPWrapper() {
    mux := http.NewServeMux()
    mux.HandleFunc("/api/health/mcp-go", func(w http.ResponseWriter, r *http.Request) {
        if r.Method != http.MethodGet {
            http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
            return
        }
        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusOK)
        _ = json.NewEncoder(w).Encode(map[string]any{
            "status":    "ok",
            "transport": "stdio",
            "service":   "mcp-connect-go",
            "ts":        time.Now().UTC().Format(time.RFC3339),
        })
    })

    addr := ":8090"
    log.Printf("mcp-connect-go HTTP wrapper listening on %s", addr)
    if err := http.ListenAndServe(addr, mux); err != nil {
        log.Printf("mcp-connect-go HTTP wrapper stopped: %v", err)
    }
}