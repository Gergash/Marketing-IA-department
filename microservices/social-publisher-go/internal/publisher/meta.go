package publisher

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const metaGraphBase = "https://graph.facebook.com/v21.0"

// isReelFormat agrupa los content_format que Meta debe rutear al branch REELS (video):
// "reel" (reel generado con IA) y "user_clip_reel" (reel armado desde clips del usuario).
func isReelFormat(contentFormat string) bool {
	return contentFormat == "reel" || contentFormat == "user_clip_reel"
}

// buildMediaParams arma los parametros del media container y el timeout de espera segun
// el content_format del request. Extraido de PublishMeta para permitir pruebas unitarias
// sin red (sin depender de httptest ni de mockear HTTPClient).
func buildMediaParams(req PublishRequest) (url.Values, time.Duration) {
	mediaParams := url.Values{
		"access_token": {req.AccessToken},
	}
	containerTimeout := mediaContainerTimeout

	switch {
	case req.ContentFormat == "story":
		mediaParams.Set("image_url", req.ImageURL)
		mediaParams.Set("media_type", "STORIES")
	case isReelFormat(req.ContentFormat):
		mediaParams.Set("video_url", req.VideoURL)
		mediaParams.Set("media_type", "REELS")
		// Reels deben poder aparecer en el feed; sin esto Meta a veces falla en media_publish (code 1).
		mediaParams.Set("share_to_feed", "true")
		caption := req.Copy
		if len(caption) > 2200 {
			caption = caption[:2200]
		}
		mediaParams.Set("caption", caption)
		containerTimeout = reelMediaContainerTimeout
	default:
		mediaParams.Set("image_url", req.ImageURL)
		caption := req.Copy
		if len(caption) > 2200 {
			caption = caption[:2200]
		}
		mediaParams.Set("caption", caption)
	}

	return mediaParams, containerTimeout
}

// PublishMeta publica en Instagram o Facebook via Graph API (2 pasos: contenedor + publish).
func PublishMeta(req PublishRequest) (PublishResponse, error) {
	igID := req.AccountID
	token := req.AccessToken

	mediaParams, containerTimeout := buildMediaParams(req)

	containerID, err := graphAPIPost(fmt.Sprintf("%s/%s/media", metaGraphBase, igID), mediaParams)
	if err != nil {
		return PublishResponse{}, fmt.Errorf("meta media_container: %w", err)
	}

	if err := waitForMediaContainer(containerID, token, containerTimeout); err != nil {
		return PublishResponse{}, fmt.Errorf("meta media_wait: %w", err)
	}

	// media_publish a veces responde OAuthException code 1 de forma transitoria justo tras FINISHED.
	var mediaID string
	var pubErr error
	for attempt := 0; attempt < 3; attempt++ {
		if attempt > 0 {
			time.Sleep(time.Duration(attempt*5) * time.Second)
		}
		mediaID, pubErr = graphAPIPost(
			fmt.Sprintf("%s/%s/media_publish", metaGraphBase, igID),
			url.Values{
				"creation_id":  {containerID},
				"access_token": {token},
			},
		)
		if pubErr == nil {
			break
		}
		if !isTransientMetaPublishError(pubErr) {
			break
		}
	}
	if pubErr != nil {
		return PublishResponse{}, fmt.Errorf("meta media_publish: %w", pubErr)
	}

	return PublishResponse{
		Status:         "published",
		PublicationURL: fmt.Sprintf("https://www.instagram.com/reel/%s/", mediaID),
		PlatformPostID: mediaID,
	}, nil
}

func isTransientMetaPublishError(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	return strings.Contains(msg, `"code":1`) ||
		strings.Contains(msg, `"code":2`) ||
		strings.Contains(msg, "unknown error") ||
		strings.Contains(msg, "unexpected error")
}

// mediaContainerTimeout es la espera máxima para contenedores de imagen/story.
const mediaContainerTimeout = 60 * time.Second

// reelMediaContainerTimeout es la espera máxima para contenedores de Reels (video),
// que Meta procesa mucho más lento que imágenes.
const reelMediaContainerTimeout = 300 * time.Second

// waitForMediaContainer espera hasta que Meta confirme status_code=FINISHED (timeout configurable).
func waitForMediaContainer(containerID, token string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		statusURL := fmt.Sprintf(
			"%s/%s?fields=status_code,status&access_token=%s",
			metaGraphBase, containerID, url.QueryEscape(token),
		)
		resp, err := HTTPClient.Get(statusURL)
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
			Status     string `json:"status"`
		}
		if json.Unmarshal(rb, &data) == nil {
			switch strings.ToUpper(data.StatusCode) {
			case "FINISHED":
				// Breve margen: publicar en el instante exacto del FINISHED a veces dispara code 1.
				time.Sleep(3 * time.Second)
				return nil
			case "ERROR":
				detail := data.Status
				if detail == "" {
					detail = string(rb)
				}
				return fmt.Errorf("contenedor en ERROR: %s", detail)
			}
		}
		time.Sleep(2 * time.Second)
	}
	return fmt.Errorf("timeout esperando status_code=FINISHED")
}

// graphAPIPost hace POST form-urlencoded al Graph API y devuelve el campo "id".
func graphAPIPost(apiURL string, params url.Values) (string, error) {
	req, err := http.NewRequest(http.MethodPost, apiURL, strings.NewReader(params.Encode()))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := HTTPClient.Do(req)
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
