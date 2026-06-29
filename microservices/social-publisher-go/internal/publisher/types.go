package publisher

// PublishRequest es el payload que recibe el sidecar desde el gateway FastAPI.
type PublishRequest struct {
	Platform       string `json:"platform"`
	Copy           string `json:"copy"`
	ImageURL       string `json:"image_url"`
	IdempotencyKey string `json:"idempotency_key"`
	ContentFormat  string `json:"content_format"`
	AccessToken    string `json:"access_token"` // OAuth 2.0 token del proveedor
	AccountID      string `json:"account_id"`   // IG Business Account ID o URN de LinkedIn
}

// PublishResponse es la respuesta normalizada para cualquier plataforma.
type PublishResponse struct {
	Status         string `json:"status"`
	PublicationURL string `json:"publication_url"`
	PlatformPostID string `json:"platform_post_id"`
}
