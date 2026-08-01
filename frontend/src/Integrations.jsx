import { useEffect, useState } from "react";

const API_BASE = (() => {
  const explicit = import.meta.env.VITE_API_URL;
  if (explicit) return String(explicit).replace(/\/$/, "") + "/api";
  if (import.meta.env.DEV) return "/api";
  return "http://localhost:8000/api";
})();

async function apiFetch(path, apiKey, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function fetchAccounts(apiKey) {
  return apiFetch("/auth/accounts", apiKey);
}

export default function Integrations({ apiKey, onAccountsChanged }) {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAccounts(apiKey);
      setAccounts(data.accounts || []);
      onAccountsChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [apiKey]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauth = params.get("oauth");
    if (oauth === "success") {
      setError(null);
      setSuccessMsg(`Cuenta ${params.get("provider") || ""} conectada correctamente.`);
      load();
    } else if (oauth === "error") {
      setSuccessMsg(null);
      setError(params.get("message") || "Error al conectar la red social");
    }
    if (oauth) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [apiKey]);

  const connectedProviders = accounts.map((c) => c.provider);

  const handleConnect = (provider) => {
    window.location.href = `${API_BASE}/auth/login/${provider}`;
  };

  const handleDisconnect = async (account) => {
    const label = account.account_name || account.account_id;
    if (!confirm(`¿Desconectar ${label} (${account.provider})?`)) return;
    setError(null);
    try {
      await apiFetch(`/auth/accounts/${account.id}`, apiKey, "DELETE");
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <section className="card">
      <h2>Integraciones de redes sociales</h2>
      <p style={{ fontSize: "0.85rem", color: "#888" }}>
        Conecta tus cuentas para publicación nativa. Meta/Instagram: OAuth + Go sidecar (:8088).
        LinkedIn: OAuth (Community Management API) + publisher nativo con imagen.
      </p>

      {error && <p style={{ color: "red", fontSize: "0.85rem" }}>{error}</p>}
      {successMsg && <p style={{ color: "#3c3", fontSize: "0.85rem" }}>{successMsg}</p>}

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
          {connectedProviders.includes("meta") ? "＋ Conectar otra cuenta Meta" : "Conectar Meta (Instagram/Facebook)"}
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
          {connectedProviders.includes("linkedin") ? "＋ Conectar otra cuenta LinkedIn" : "Conectar LinkedIn"}
        </button>

        <button onClick={load} disabled={loading} style={{ background: "transparent", border: "1px solid #666", padding: "0.6rem 1rem", borderRadius: "6px", cursor: "pointer" }}>
          {loading ? "..." : "Refrescar"}
        </button>
      </div>

      {accounts.length > 0 && (
        <table style={{ fontSize: "0.8rem", borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #444" }}>
              <th style={{ padding: "4px 8px" }}>Cuenta</th>
              <th style={{ padding: "4px 8px" }}>Proveedor</th>
              <th style={{ padding: "4px 8px" }}>Account ID</th>
              <th style={{ padding: "4px 8px" }}>Actualizado</th>
              <th style={{ padding: "4px 8px" }}></th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((c) => (
              <tr key={c.id}>
                <td style={{ padding: "4px 8px", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  {c.profile_picture_url && (
                    <img
                      src={c.profile_picture_url}
                      alt=""
                      style={{ width: 24, height: 24, borderRadius: "50%", objectFit: "cover" }}
                    />
                  )}
                  {c.account_name || "—"}
                </td>
                <td style={{ padding: "4px 8px" }}><code>{c.provider}</code></td>
                <td style={{ padding: "4px 8px" }}><code>{c.account_id}</code></td>
                <td style={{ padding: "4px 8px", color: "#888" }}>{new Date(c.updated_at).toLocaleString()}</td>
                <td style={{ padding: "4px 8px" }}>
                  <button
                    onClick={() => handleDisconnect(c)}
                    style={{ background: "transparent", border: "1px solid #a33", color: "#c66", padding: "2px 8px", borderRadius: "4px", cursor: "pointer" }}
                  >
                    Desconectar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <details style={{ marginTop: "0.75rem", fontSize: "0.8rem", color: "#888" }}>
        <summary>Configuración necesaria (.env)</summary>
        <pre style={{ marginTop: "0.5rem", background: "#1a1a2e", padding: "0.75rem", borderRadius: "4px" }}>{`# Meta OAuth
META_CLIENT_ID=...
META_CLIENT_SECRET=...
META_REDIRECT_URI=http://localhost:8000/api/auth/callback/meta

# LinkedIn OAuth (Community Management API + OpenID)
# Redirect URI en LinkedIn Developers debe coincidir EXACTO
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_REDIRECT_URI=http://localhost:8000/api/auth/callback/linkedin

# URL pública de imágenes (ngrok para Meta; LinkedIn imagen también si localhost)
PUBLIC_IMAGE_BASE_URL=https://xxxx.ngrok-free.dev`}</pre>
      </details>
    </section>
  );
}
