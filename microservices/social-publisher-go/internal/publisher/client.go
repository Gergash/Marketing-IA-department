package publisher

import (
	"io"
	"net/http"
	"time"
)

// HTTPClient es el cliente HTTP compartido por todos los providers.
var HTTPClient = &http.Client{Timeout: 60 * time.Second}

// downloadImage descarga la imagen desde imageURL y devuelve los bytes y el Content-Type.
// Para LinkedIn la imagen puede venir de localhost directamente (no necesita ngrok).
func downloadImage(imageURL string) ([]byte, string, error) {
	resp, err := HTTPClient.Get(imageURL)
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
