package publisher

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// PublishLinkedIn orquesta los 3 pasos de publicación nativa con imagen en LinkedIn.
func PublishLinkedIn(req PublishRequest) (PublishResponse, error) {
	token := req.AccessToken
	personURN := req.AccountID // "urn:li:person:XXXXX"

	// Paso 1: Descargar imagen (localhost accesible directamente; no requiere ngrok).
	imgBytes, contentType, err := downloadImage(req.ImageURL)
	if err != nil {
		return PublishResponse{}, fmt.Errorf("descargar imagen: %w", err)
	}

	// Paso 2: Registrar el upload y obtener la URL firmada + URN del asset.
	assetURN, uploadURL, err := linkedInRegisterUpload(token, personURN)
	if err != nil {
		return PublishResponse{}, fmt.Errorf("linkedin register upload: %w", err)
	}

	// Paso 3: Subir los bytes de la imagen al endpoint firmado de LinkedIn.
	if err := linkedInUploadImage(uploadURL, token, imgBytes, contentType); err != nil {
		return PublishResponse{}, fmt.Errorf("linkedin upload imagen: %w", err)
	}

	// Paso 4: Crear el UGC Post referenciando el asset ya subido.
	postID, err := linkedInCreatePost(token, personURN, req.Copy, assetURN)
	if err != nil {
		return PublishResponse{}, fmt.Errorf("linkedin crear post: %w", err)
	}

	return PublishResponse{
		Status:         "published",
		PublicationURL: fmt.Sprintf("https://www.linkedin.com/feed/update/%s/", postID),
		PlatformPostID: postID,
	}, nil
}

// linkedInRegisterUpload llama a /rest/images?action=initializeUpload para registrar
// la imagen y obtener la URL de upload firmada y el URN del asset.
func linkedInRegisterUpload(token, ownerURN string) (assetURN, uploadURL string, err error) {
	body := map[string]any{
		"initializeUploadRequest": map[string]any{
			"owner": ownerURN,
		},
	}
	b, _ := json.Marshal(body)

	req, _ := http.NewRequest(
		http.MethodPost,
		"https://api.linkedin.com/rest/images?action=initializeUpload",
		bytes.NewReader(b),
	)
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("LinkedIn-Version", "202401")
	req.Header.Set("X-Restli-Protocol-Version", "2.0.0")

	resp, err := HTTPClient.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()
	rb, _ := io.ReadAll(resp.Body)

	if resp.StatusCode >= 400 {
		return "", "", fmt.Errorf("linkedin initializeUpload HTTP %d: %s", resp.StatusCode, string(rb))
	}

	var data struct {
		Value struct {
			UploadURL string `json:"uploadUrl"`
			Image     string `json:"image"` // URN del asset: "urn:li:image:..."
		} `json:"value"`
	}
	if err := json.Unmarshal(rb, &data); err != nil {
		return "", "", fmt.Errorf("parse linkedin initializeUpload: %w", err)
	}
	if data.Value.UploadURL == "" || data.Value.Image == "" {
		return "", "", fmt.Errorf("linkedin initializeUpload: uploadUrl o image URN vacíos — %s", string(rb))
	}
	return data.Value.Image, data.Value.UploadURL, nil
}

// linkedInUploadImage hace PUT de los bytes de imagen al URL firmado devuelto por initializeUpload.
func linkedInUploadImage(uploadURL, token string, imgBytes []byte, contentType string) error {
	req, _ := http.NewRequest(http.MethodPut, uploadURL, bytes.NewReader(imgBytes))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", contentType)

	resp, err := HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	// LinkedIn devuelve 201 en uploads exitosos.
	if resp.StatusCode >= 400 {
		rb, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("linkedin upload binario HTTP %d: %s", resp.StatusCode, string(rb))
	}
	return nil
}

// linkedInCreatePost crea el UGC Post con la imagen ya subida referenciada por su URN.
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

	resp, err := HTTPClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	rb, _ := io.ReadAll(resp.Body)

	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("linkedin ugcPosts HTTP %d: %s", resp.StatusCode, string(rb))
	}

	// El post ID viene en el header x-restli-id o en el body.
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
