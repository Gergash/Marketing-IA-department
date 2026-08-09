package publisher

import (
	"net/http"
	"time"
)

// HTTPClient es el cliente HTTP compartido por todos los providers.
var HTTPClient = &http.Client{Timeout: 60 * time.Second}
