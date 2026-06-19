import { useEffect, useState } from "react";
import Integrations from "./Integrations";

// ---------------------------------------------------------------------------
// API key — almacenada en sessionStorage (no persiste entre sesiones)
// ---------------------------------------------------------------------------
function getApiKey() {
  return sessionStorage.getItem("api_key") || import.meta.env.VITE_API_KEY || "";
}

function saveApiKey(key) {
  sessionStorage.setItem("api_key", key);
}

// ---------------------------------------------------------------------------
// Cliente HTTP base
// ---------------------------------------------------------------------------
function apiOrigin() {
  const explicit = import.meta.env.VITE_API_URL;
  if (explicit) return String(explicit).replace(/\/$/, "");
  if (import.meta.env.DEV) return "";
  return "http://localhost:8000";
}

const API_BASE = `${apiOrigin()}/api`;

/** Convierte URL absoluta del backend a ruta relativa servida por el proxy Vite. */
function resolveImageUrl(url) {
  if (!url) return url;
  try {
    const parsed = new URL(url);
    if (parsed.pathname.startsWith("/static/")) {
      return parsed.pathname;
    }
  } catch {
    if (url.startsWith("/static/")) return url;
  }
  return url;
}

async function api(path, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  const key = getApiKey();
  if (key) headers["Authorization"] = `Bearer ${key}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------
export default function App() {
  const [apiKey, setApiKey] = useState(getApiKey());
  const [keyInput, setKeyInput] = useState("");
  const [form, setForm] = useState({
    tema: "",
    publico_objetivo: "",
    red_social: "instagram",
    objetivo: "branding",
    tono_marca: "profesional y cercano",
  });
  const [socialStatus, setSocialStatus] = useState(null);
  const [contentFormat, setContentFormat] = useState("feed");
  const [imageProvider, setImageProvider] = useState("fal");
  const [imageProviders, setImageProviders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [approvingRunId, setApprovingRunId] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);

  const loadHistory = async () => {
    try {
      const data = await api("/runs");
      setHistory(Array.isArray(data) ? data : data.runs ?? []);
    } catch {
      setHistory([]);
    }
  };

  const loadSocialStatus = async () => {
    try {
      const s = await api("/social/publish-status");
      setSocialStatus(s);
    } catch {
      setSocialStatus(null);
    }
  };

  const loadImageProviders = async () => {
    try {
      const data = await api("/image/providers");
      const list = Array.isArray(data.providers) ? data.providers : [];
      setImageProviders(list);
      if (list.length > 0) {
        const defaultId = data.default_provider;
        const hasDefault = list.some((p) => p.id === defaultId);
        setImageProvider(hasDefault ? defaultId : list[0].id);
      }
    } catch {
      setImageProviders([
        { id: "stable_diffusion", label: "Stable Diffusion" },
        { id: "fal", label: "fal.ai (Flux)" },
      ]);
    }
  };

  useEffect(() => {
    loadHistory();
    loadSocialStatus();
    loadImageProviders();
  }, [apiKey]);

  const applyKey = () => {
    saveApiKey(keyInput.trim());
    setApiKey(keyInput.trim());
    setKeyInput("");
    setError(null);
  };

  const createAndRun = async (asyncMode = false) => {
    setLoading(true);
    setError(null);
    try {
      const brief = await api("/briefs", "POST", form);
      const runReq = {
        brief_id: brief.id,
        publish: true,
        requires_approval: true,         // human-in-the-loop activo por defecto
        idempotency_key: `${brief.id}-${Date.now()}`,
        content_format: contentFormat,
        image_provider: imageProvider,
      };
      const run = await api(asyncMode ? "/runs/async" : "/runs/sync", "POST", runReq);
      setResult({ run_id: run.run_id, status: run.status, result: run.result });
      await loadHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const doApprove = async (runId) => {
    if (approvingRunId != null) return;
    setApprovingRunId(runId);
    setError(null);
    try {
      await api(`/runs/${runId}/approve`, "POST", { approved_by: "human" });
      const updated = await api(`/runs/${runId}`);
      setResult({ run_id: updated.run_id, status: updated.status, result: updated.result });
      await loadHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setApprovingRunId(null);
    }
  };

  const doReject = async (runId) => {
    const reason = prompt("Motivo del rechazo (opcional):");
    setError(null);
    try {
      await api(`/runs/${runId}/reject`, "POST", { reason: reason || "", approved_by: "human" });
      await loadHistory();
    } catch (e) {
      setError(e.message);
    }
  };

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <main className="container">
      <h1>Marketing DEPA IA — MVP Dashboard</h1>

      {/* API Key */}
      <section className="card">
        <h2>Autenticación</h2>
        {apiKey ? (
          <p>
            API Key activa: <code>{"•".repeat(8)}</code>{" "}
            <button onClick={() => { saveApiKey(""); setApiKey(""); }}>Cambiar</button>
          </p>
        ) : (
          <div className="actions">
            <input
              placeholder="API_KEY (vacío = dev sin auth)"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyKey()}
            />
            <button onClick={applyKey}>Guardar</button>
          </div>
        )}
      </section>

      {/* Integraciones OAuth */}
      <Integrations apiKey={apiKey} />

      {/* Estado redes (sin secretos) */}
      <section className="card">
        <h2>Publicación en redes</h2>
        {socialStatus ? (
          <ul style={{ fontSize: "0.9rem" }}>
            <li><strong>Proveedor activo:</strong> <code>{socialStatus.social_provider}</code></li>
            <li>LinkedIn listo: {socialStatus.linkedin_ready ? "sí" : "no"}</li>
            <li>Upload-Post listo: {socialStatus.uploadpost_ready ? "sí" : "no"}</li>
            <li>Meta / Instagram (credenciales): {socialStatus.meta_instagram_ready ? "sí" : "no"}</li>
          </ul>
        ) : (
          <p style={{ color: "#888" }}>No se pudo cargar el estado (¿API caída?).</p>
        )}
        <p style={{ fontSize: "0.8rem", color: "#888" }}>{socialStatus?.hint}</p>
        <label>
          Formato de publicación
          <select value={contentFormat} onChange={(e) => setContentFormat(e.target.value)}>
            <option value="feed">Post en feed (Instagram 1080×1350, 4:5)</option>
            <option value="story">Historia (Instagram 1080×1920)</option>
          </select>
        </label>
        <p className="hint">
          Las dimensiones de la imagen se ajustan según <code>red_social</code> del brief y este formato.
        </p>
      </section>

      {/* Formulario */}
      <section className="card">
        <h2>Nuevo Brief</h2>
        <div className="image-provider-block">
          <span className="field-label">Generador de imagen</span>
          <div className="segmented-control" role="group" aria-label="Generador de imagen">
            {(imageProviders.length > 0
              ? imageProviders
              : [
                  { id: "stable_diffusion", label: "Stable Diffusion" },
                  { id: "fal", label: "fal.ai (Flux)" },
                ]
            ).map((provider) => (
              <button
                key={provider.id}
                type="button"
                className={`segment ${imageProvider === provider.id ? "segment-active" : ""}`}
                disabled={loading}
                onClick={() => setImageProvider(provider.id)}
              >
                {provider.label}
              </button>
            ))}
          </div>
          <p className="hint">
            {imageProvider === "fal"
              ? "Flux Pro vía API en la nube (requiere FAL_API_KEY en el servidor)."
              : "Generación local con Automatic1111/Forge en :7860."}
          </p>
        </div>
        {Object.keys(form).map((key) => (
          <label key={key}>
            {key}
            <input
              value={form[key]}
              onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
            />
          </label>
        ))}
        <div className="actions">
          <button disabled={loading} onClick={() => createAndRun(false)}>
            Ejecutar Sync
          </button>
          <button disabled={loading} onClick={() => createAndRun(true)}>
            Enviar Async
          </button>
        </div>
        <p style={{ fontSize: "0.8rem", color: "#888" }}>
          Requiere aprobación humana activada por defecto (human-in-the-loop).
        </p>
      </section>

      {/* Resultado */}
      <section className="card">
        <h2>Resultado</h2>
        {error && <p style={{ color: "red" }}>{error}</p>}
        {result?.result?.design?.image_url && (
          <div style={{ marginBottom: "1rem" }}>
            <p style={{ fontSize: "0.85rem", color: "#888", marginBottom: "0.4rem" }}>
              Imagen generada
              {result.result.design.image_provider && (
                <> — <code>{result.result.design.image_provider}</code></>
              )}
              {result.result.design.image_width > 0 && (
                <> · {result.result.design.image_width}×{result.result.design.image_height}px</>
              )}
              {result.result.design.content_format && (
                <> · {result.result.design.content_format}</>
              )}
              {result.result.design.layout_label && (
                <> · layout: {result.result.design.layout_label}</>
              )}
              :
            </p>
            <img
              src={resolveImageUrl(result.result.design.image_url)}
              alt="Imagen generada"
              style={{ maxWidth: "100%", borderRadius: "6px", border: "1px solid #333" }}
            />
          </div>
        )}
        <pre>{result ? JSON.stringify(result, null, 2) : "Sin ejecución sincrónica aún."}</pre>
      </section>

      {/* Historial */}
      <section className="card">
        <h2>Historial de ejecuciones</h2>
        <button onClick={loadHistory} style={{ marginBottom: "0.5rem" }}>Refrescar</button>
        <ul>
          {history.map((item) => (
            <li key={item.run_id} style={{ marginBottom: "0.5rem" }}>
              <strong>#{item.run_id}</strong> — <code>{item.status}</code>
              {item.content_format && (
                <span style={{ marginLeft: "0.5rem", color: "#666" }}>({item.content_format})</span>
              )}
              {item.approved_by && (
                <span style={{ marginLeft: "0.5rem", color: "#888" }}>
                  (por {item.approved_by})
                </span>
              )}
              {item.status === "pending_approval" && (
                <span style={{ marginLeft: "1rem" }}>
                  <button
                    disabled={approvingRunId != null}
                    onClick={() => doApprove(item.run_id)}
                    style={{ marginRight: "0.3rem" }}
                  >
                    {approvingRunId === item.run_id ? "Publicando…" : "✓ Aprobar"}
                  </button>
                  <button disabled={approvingRunId != null} onClick={() => doReject(item.run_id)}>✗ Rechazar</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
