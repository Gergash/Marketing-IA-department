import { useEffect, useState } from "react";

const API_BASE = (() => {
  const explicit = import.meta.env.VITE_API_URL;
  if (explicit) return String(explicit).replace(/\/$/, "") + "/api";
  if (import.meta.env.DEV) return "/api";
  return "http://localhost:8000/api";
})();

async function fetchStatus(apiKey) {
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
  const res = await fetch(`${API_BASE}/auth/status`, { headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export default function Integrations({ apiKey }) {
  const [connected, setConnected] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchStatus(apiKey);
      setConnected(data.connected || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [apiKey]);

  const connectedProviders = connected.map((c) => c.provider);

  const handleConnect = (provider) => {
    // Abre el flujo OAuth en la misma pestaña; al callback regresa al usuario con JSON de confirmación.
    window.location.href = `${API_BASE}/auth/login/${provider}`;
  };

  return (
    <section className="card">
      <h2>Integraciones de redes sociales</h2>
      <p style={{ fontSize: "0.85rem", color: "#888" }}>
        Conecta tus cuentas para que el agente publique directamente usando OAuth 2.0 nativo.
        {" "}La URL de callback debe coincidir con la configurada en el panel de desarrollador de cada red.
      </p>

      {error && <p style={{ color: "red", fontSize: "0.85rem" }}>{error}</p>}

      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginBottom: "1rem" }}>
        <button
          onClick={() => handleConnect("meta")}
          style={{
            background: connectedProviders.includes("meta") ? "#1877f2" : "#444",
            color: "#fff",
            border: "none",
            padding: "0.6rem 1.2rem",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
        >
          {connectedProviders.includes("meta") ? "✓ Meta (Instagram/Facebook) conectado" : "Conectar Meta (Instagram/Facebook)"}
        </button>

        <button
          onClick={() => handleConnect("linkedin")}
          style={{
            background: connectedProviders.includes("linkedin") ? "#0a66c2" : "#444",
            color: "#fff",
            border: "none",
            padding: "0.6rem 1.2rem",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
        >
          {connectedProviders.includes("linkedin") ? "✓ LinkedIn conectado" : "Conectar LinkedIn"}
        </button>

        <button onClick={load} disabled={loading} style={{ background: "transparent", border: "1px solid #666", padding: "0.6rem 1rem", borderRadius: "6px", cursor: "pointer" }}>
          {loading ? "..." : "Refrescar"}
        </button>
      </div>

      {connected.length > 0 && (
        <table style={{ fontSize: "0.8rem", borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #444" }}>
              <th style={{ padding: "4px 8px" }}>Proveedor</th>
              <th style={{ padding: "4px 8px" }}>Account ID</th>
              <th style={{ padding: "4px 8px" }}>Actualizado</th>
            </tr>
          </thead>
          <tbody>
            {connected.map((c) => (
              <tr key={c.provider}>
                <td style={{ padding: "4px 8px" }}><code>{c.provider}</code></td>
                <td style={{ padding: "4px 8px" }}><code>{c.account_id}</code></td>
                <td style={{ padding: "4px 8px", color: "#888" }}>{new Date(c.updated_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <details style={{ marginTop: "0.75rem", fontSize: "0.8rem", color: "#888" }}>
        <summary>Configuración necesaria (.env)</summary>
        <pre style={{ marginTop: "0.5rem", background: "#1a1a2e", padding: "0.75rem", borderRadius: "4px" }}>{`# Meta
META_CLIENT_ID=...
META_CLIENT_SECRET=...
META_REDIRECT_URI=http://localhost:8000/api/auth/callback/meta

# LinkedIn
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_REDIRECT_URI=http://localhost:8000/api/auth/callback/linkedin

# URL pública de imágenes (ngrok para dev — Meta requiere HTTPS)
PUBLIC_IMAGE_BASE_URL=https://xxxx.ngrok.io`}</pre>
      </details>
    </section>
  );
}
