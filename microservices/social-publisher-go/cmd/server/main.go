package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// ---------------------------------------------------------------------------
// Tipos de request/response
// ---------------------------------------------------------------------------

type publishRequest struct {
	Platform       string `json:"platform"`
	Copy           string `json:"copy"`
	ImageURL       string `json:"image_url"`
	IdempotencyKey string `json:"idempotency_key"`
	ContentFormat  string `json:"content_format"`
	AccessToken    string `json:"access_token"`  // OAuth 2.0 token del proveedor
	AccountID      string `json:"account_id"`    // IG Business Account ID o URN de LinkedIn
}

type publishResponse struct {
	Status         string `json:"status"`
	PublicationURL string `json:"publication_url"`
	PlatformPostID string `json:"platform_post_id"`
}

var httpClient = &http.Client{Timeout: 60 * time.Second}

// ---------------------------------------------------------------------------
// Handlers HTTP
// ---------------------------------------------------------------------------

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok","service":"social-publisher-go"}`))
}

func publishHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req publishRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid payload", http.StatusBadRequest)
		return
	}

	if req.AccessToken == "" {
		log.Printf("[WARN] no access_token para platform=%s — respondiendo mock", req.Platform)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(publishResponse{
			Status:         "mock_no_token",
			PublicationURL: fmt.Sprintf("https://social.mock/%s/posts/no-token", req.Platform),
			PlatformPostID: "mock-no-token",
		})
		return
	}

	platform := strings.ToLower(req.Platform)
	var resp publishResponse
	var err error

	switch {
	case platform == "instagram" || platform == "ig" || platform == "facebook":
		resp, err = publishMeta(req)
	case platform == "linkedin":
		resp, err = publishLinkedIn(req)
	default:
		http.Error(w, fmt.Sprintf("plataforma no soportada: %s", req.Platform), http.StatusBadRequest)
		return
	}

	if err != nil {
		log.Printf("[ERROR] publish %s: %v", req.Platform, err)
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}

// ---------------------------------------------------------------------------
// Meta Graph API — Instagram (2 pasos: contenedor + publicación)
// Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing
// ---------------------------------------------------------------------------

func publishMeta(req publishRequest) (publishResponse, error) {
	const graphBase = "https://graph.facebook.com/v21.0"
	igID := req.AccountID
	token := req.AccessToken

	// Paso 1: Crear contenedor de media
	mediaParams := url.Values{
		"image_url":    {req.ImageURL},
		"access_token": {token},
	}
	if req.ContentFormat == "story" {
		mediaParams.Set("media_type", "STORIES")
	} else {
		caption := req.Copy
		if len(caption) > 2200 {
			caption = caption[:2200]
		}
		mediaParams.Set("caption", caption)
	}

	containerID, err := graphAPIPost(fmt.Sprintf("%s/%s/media", graphBase, igID), mediaParams)
	if err != nil {
		return publishResponse{}, fmt.Errorf("meta media_container: %w", err)
	}

	if err := waitForMediaContainer(graphBase, containerID, token); err != nil {
		return publishResponse{}, fmt.Errorf("meta media_wait: %w", err)
	}

	// Paso 2: Publicar el contenedor
	mediaID, err := graphAPIPost(
		fmt.Sprintf("%s/%s/media_publish", graphBase, igID),
		url.Values{
			"creation_id":  {containerID},
			"access_token": {token},
		},
	)
	if err != nil {
		return publishResponse{}, fmt.Errorf("meta media_publish: %w", err)
	}

	log.Printf("[INFO] meta published media_id=%s", mediaID)
	return publishResponse{
		Status:         "published",
		PublicationURL: fmt.Sprintf("https://www.instagram.com/p/%s/", mediaID),
		PlatformPostID: mediaID,
	}, nil
}

func waitForMediaContainer(graphBase, containerID, token string) error {
	deadline := time.Now().Add(60 * time.Second)
	for time.Now().Before(deadline) {
		statusURL := fmt.Sprintf("%s/%s?fields=status_code&access_token=%s", graphBase, containerID, url.QueryEscape(token))
		resp, err := httpClient.Get(statusURL)
		if err != nil {
			return err
		}
		rb, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		if resp.StatusCode >= 400 {
			return fmt.Errorf("graph API HTTP %d: %s", resp.StatusCode, string(rb))
		}
		var data struct {
			StatusCode string `json:"status_code"`
		}
		if json.Unmarshal(rb, &data) == nil {
			switch strings.ToUpper(data.StatusCode) {
			case "FINISHED":
				return nil
			case "ERROR":
				return fmt.Errorf("contenedor en ERROR: %s", string(rb))
			}
		}
		time.Sleep(2 * time.Second)
	}
	return fmt.Errorf("timeout esperando status_code=FINISHED")
}

// graphAPIPost hace POST form-urlencoded al Graph API y devuelve el campo "id" de la respuesta JSON.
func graphAPIPost(apiURL string, params url.Values) (string, error) {
	req, err := http.NewRequest(http.MethodPost, apiURL, strings.NewReader(params.Encode()))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	rb, _ := io.ReadAll(resp.Body)

	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("graph API HTTP %d: %s", resp.StatusCode, string(rb))
	}

	var data map[string]any
	if err := json.Unmarshal(rb, &data); err != nil {
		return "", fmt.Errorf("parse graph response: %w", err)
	}
	switch v := data["id"].(type) {
	case string:
		return v, nil
	case float64:
		return fmt.Sprintf("%.0f", v), nil
	default:
		return "", fmt.Errorf("sin campo 'id' en respuesta: %s", string(rb))
	}
}

// ---------------------------------------------------------------------------
// LinkedIn UGC Posts API con imagen
// Docs: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/images-api
// ---------------------------------------------------------------------------

func publishLinkedIn(req publishRequest) (publishResponse, error) {
	token := req.AccessToken
	personURN := req.AccountID // "urn:li:person:XXXXX"

	// Paso 1: Descargar imagen desde la URL local/pública
	imgBytes, contentType, err := downloadImage(req.ImageURL)
	if err != nil {
		return publishResponse{}, fmt.Errorf("descargar imagen: %w", err)
	}

	// Paso 2: Inicializar upload de imagen en LinkedIn
	assetURN, uploadURL, err := linkedInInitImageUpload(token, personURN)
	if err != nil {
		return publishResponse{}, fmt.Errorf("linkedin init upload: %w", err)
	}

	// Paso 3: Subir bytes de imagen al URL de upload firmado
	if err := linkedInUploadImage(uploadURL, imgBytes, contentType); err != nil {
		return publishResponse{}, fmt.Errorf("linkedin upload imagen: %w", err)
	}

	// Paso 4: Crear UGC Post con la imagen como media
	postID, err := linkedInCreatePost(token, personURN, req.Copy, assetURN)
	if err != nil {
		return publishResponse{}, fmt.Errorf("linkedin crear post: %w", err)
	}

	log.Printf("[INFO] linkedin published post_id=%s", postID)
	return publishResponse{
		Status:         "published",
		PublicationURL: fmt.Sprintf("https://www.linkedin.com/feed/update/%s/", postID),
		PlatformPostID: postID,
	}, nil
}

func downloadImage(imageURL string) ([]byte, string, error) {
	resp, err := httpClient.Get(imageURL)
	if err != nil {
		return nil, "", err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	ct := resp.Header.Get("Content-Type")
	if ct == "" {
		ct = "image/png"
	}
	return b, ct, err
}

func linkedInInitImageUpload(token, ownerURN string) (assetURN, uploadURL string, err error) {
	body := map[string]any{
		"initializeUploadRequest": map[string]any{
			"owner": ownerURN,
		},
	}
	b, _ := json.Marshal(body)

	req, _ := http.NewRequest(http.MethodPost,
		"https://api.linkedin.com/rest/images?action=initializeUpload",
		bytes.NewReader(b))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("LinkedIn-Version", "202304")
	req.Header.Set("X-Restli-Protocol-Version", "2.0.0")

	resp, err := httpClient.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()
	rb, _ := io.ReadAll(resp.Body)

	if resp.StatusCode >= 400 {
		return "", "", fmt.Errorf("linkedin init upload HTTP %d: %s", resp.StatusCode, string(rb))
	}

	var data struct {
		Value struct {
			UploadURL string `json:"uploadUrl"`
			Image     string `json:"image"`
		} `json:"value"`
	}
	if err := json.Unmarshal(rb, &data); err != nil {
		return "", "", fmt.Errorf("parse linkedin init: %w", err)
	}
	return data.Value.Image, data.Value.UploadURL, nil
}

func linkedInUploadImage(uploadURL string, imgBytes []byte, contentType string) error {
	req, _ := http.NewRequest(http.MethodPut, uploadURL, bytes.NewReader(imgBytes))
	req.Header.Set("Content-Type", contentType)

	resp, err := httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		rb, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("linkedin upload HTTP %d: %s", resp.StatusCode, string(rb))
	}
	return nil
}

func linkedInCreatePost(token, authorURN, copyText, imageURN string) (string, error) {
	if len(copyText) > 3000 {
		copyText = copyText[:3000]
	}
	body := map[string]any{
		"author":         authorURN,
		"lifecycleState": "PUBLISHED",
		"specificContent": map[string]any{
			"com.linkedin.ugc.ShareContent": map[string]any{
				"shareCommentary":    map[string]any{"text": copyText},
				"shareMediaCategory": "IMAGE",
				"media": []map[string]any{
					{
						"status":      "READY",
						"description": map[string]any{"text": ""},
						"media":       imageURN,
					},
				},
			},
		},
		"visibility": map[string]any{
			"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
		},
	}
	b, _ := json.Marshal(body)

	req, _ := http.NewRequest(http.MethodPost, "https://api.linkedin.com/v2/ugcPosts", bytes.NewReader(b))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Restli-Protocol-Version", "2.0.0")

	resp, err := httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	rb, _ := io.ReadAll(resp.Body)

	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("linkedin ugcPosts HTTP %d: %s", resp.StatusCode, string(rb))
	}

	postID := resp.Header.Get("x-restli-id")
	if postID == "" {
		var data map[string]any
		if json.Unmarshal(rb, &data) == nil {
			if id, ok := data["id"].(string); ok {
				postID = id
			}
		}
	}
	if postID == "" {
		postID = "unknown"
	}
	return postID, nil
}

// ---------------------------------------------------------------------------
// Punto de entrada
// ---------------------------------------------------------------------------

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/publish", publishHandler)

	addr := ":8088"
	log.Printf("social-publisher-go escuchando en %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}
