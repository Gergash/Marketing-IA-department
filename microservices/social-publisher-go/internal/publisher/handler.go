package publisher

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
)

func HealthHandler(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok","service":"social-publisher-go"}`))
}

func PublishHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req PublishRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid payload", http.StatusBadRequest)
		return
	}

	if req.AccessToken == "" {
		log.Printf("[WARN] no access_token para platform=%s — respondiendo mock", req.Platform)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(PublishResponse{
			Status:         "mock_no_token",
			PublicationURL: fmt.Sprintf("https://social.mock/%s/posts/no-token", req.Platform),
			PlatformPostID: "mock-no-token",
		})
		return
	}

	platform := strings.ToLower(req.Platform)
	var (
		resp PublishResponse
		err  error
	)

	switch {
	case platform == "instagram" || platform == "ig" || platform == "facebook":
		resp, err = PublishMeta(req)
	case platform == "linkedin":
		// LinkedIn se publica nativamente desde el gateway Python (/rest/posts);
		// el sidecar solo cubre Meta. Llegar aquí significa routing mal configurado.
		http.Error(w, "linkedin se publica desde el gateway Python, no por el sidecar Go", http.StatusBadRequest)
		return
	default:
		http.Error(w, fmt.Sprintf("plataforma no soportada: %s", req.Platform), http.StatusBadRequest)
		return
	}

	if err != nil {
		log.Printf("[ERROR] publish %s: %v", req.Platform, err)
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}

	log.Printf("[INFO] published platform=%s post_id=%s", req.Platform, resp.PlatformPostID)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}
