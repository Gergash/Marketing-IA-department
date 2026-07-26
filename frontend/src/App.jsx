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

async function uploadAsset(file) {
  const headers = {};
  const key = getApiKey();
  if (key) headers["Authorization"] = `Bearer ${key}`;
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_BASE}/briefs/upload-asset`, {
    method: "POST",
    headers,
    body,
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
  const [archetypeOverride, setArchetypeOverride] = useState("");
  const [archetypes, setArchetypes] = useState([]);
  const [userAssetUrl, setUserAssetUrl] = useState("");
  const [userAssetName, setUserAssetName] = useState("");
  const [driveFolderId, setDriveFolderId] = useState("");
  const [alterImageWithAi, setAlterImageWithAi] = useState(false);
  const [visualInstructions, setVisualInstructions] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [approvingRunId, setApprovingRunId] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  // Stub de edición: instrucciones de cambio locales hasta conectar POST /runs/{id}/revise
  const [revisionNotes, setRevisionNotes] = useState("");
  const [revisionByRunId, setRevisionByRunId] = useState({});
  const [revisionFeedback, setRevisionFeedback] = useState(null);

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

  const loadArchetypes = async () => {
    try {
      const data = await api("/image/archetypes");
      setArchetypes(Array.isArray(data) ? data : []);
    } catch {
      setArchetypes([
        { id: "typographic_poster", label: "Poster tipográfico" },
        { id: "minimal_conceptual", label: "Conceptual minimal" },
        { id: "editorial_infographic", label: "Infográfico editorial" },
        { id: "cinematic_hero", label: "Hero cinematográfico" },
      ]);
    }
  };

  useEffect(() => {
    loadHistory();
    loadSocialStatus();
    loadImageProviders();
    loadArchetypes();
  }, [apiKey]);

  const applyKey = () => {
    saveApiKey(keyInput.trim());
    setApiKey(keyInput.trim());
    setKeyInput("");
    setError(null);
  };

  const createAndRun = async (asyncMode = false) => {
    // Los reels (generados o con clips del usuario) se procesan en la cola video_render
    // y tardan minutos: no admiten /runs/sync (422).
    const isVideoFormat = contentFormat === "reel" || contentFormat === "user_clip_reel";
    const effectiveAsync = isVideoFormat ? true : asyncMode;
    setLoading(true);
    setError(null);
    try {
      const brief = await api("/briefs", "POST", form);
      const runReq = {
        brief_id: brief.id,
        publish: true,
        requires_approval: true,
        idempotency_key: `${brief.id}-${Date.now()}`,
        content_format: contentFormat,
        image_provider: imageProvider,
        ...(archetypeOverride ? { archetype_override: archetypeOverride } : {}),
        ...(userAssetUrl ? { user_asset_url: userAssetUrl } : {}),
        ...(userAssetUrl && alterImageWithAi ? { alter_image_with_ai: true } : {}),
        ...(userAssetUrl && alterImageWithAi && visualInstructions.trim()
          ? { visual_instructions: visualInstructions.trim() }
          : {}),
        ...(contentFormat === "user_clip_reel" ? { drive_folder_id: driveFolderId.trim() } : {}),
      };
      const run = await api(effectiveAsync ? "/runs/async" : "/runs/sync", "POST", runReq);
      setResult({ run_id: run.run_id, status: run.status, result: run.result });
      setRevisionNotes("");
      setRevisionFeedback(null);
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

  /** Stub: captura instrucciones de edición sin llamar al pipeline todavía. */
  const requestRevision = (runId, notes) => {
    const trimmed = (notes || "").trim();
    if (!trimmed) {
      setRevisionFeedback({
        runId: runId ?? null,
        ok: false,
        message: "Escribe qué quieres cambiar en la pieza antes de solicitar cambios.",
      });
      return;
    }
    if (runId != null) {
      setRevisionByRunId((prev) => ({ ...prev, [runId]: trimmed }));
    } else {
      setRevisionNotes(trimmed);
    }
    setRevisionFeedback({
      runId: runId ?? null,
      ok: true,
      message: "Instrucción guardada; conexión al pipeline pendiente.",
    });
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
            <li>LinkedIn listo: {socialStatus.linkedin_ready ? "sí" : "no"}
              {socialStatus.linkedin_oauth_connected ? " (OAuth)" : ""}
            </li>
            <li>Meta OAuth conectado: {socialStatus.meta_oauth_connected ? "sí" : "no"}</li>
            <li>Go publisher: <code>{socialStatus.go_publisher_url || "http://localhost:8088"}</code></li>
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
            <option value="reel">Reel (Instagram 1080×1920, video)</option>
            <option value="user_clip_reel">Video con mis clips (Drive)</option>
          </select>
        </label>
        <p className="hint">
          Las dimensiones de la imagen se ajustan según <code>red_social</code> del brief y este formato.
          {(contentFormat === "reel" || contentFormat === "user_clip_reel") &&
            " Los reels son async-only: se envían siempre con \"Enviar Async\"."}
        </p>
        {contentFormat === "user_clip_reel" && (
          <label>
            Carpeta de Drive (ID)
            <input
              placeholder="ID de la carpeta de Google Drive con tus clips"
              value={driveFolderId}
              onChange={(e) => setDriveFolderId(e.target.value)}
            />
          </label>
        )}
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
        <div className="archetype-block">
          <label>
            Arquetipo visual
            <select
              value={archetypeOverride}
              disabled={loading}
              onChange={(e) => setArchetypeOverride(e.target.value)}
            >
              <option value="">Automático (el agente elige)</option>
              {archetypes.map((a) => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
          </label>
          <p className="hint">
            Fuerza un arquetipo o deja que el agente lo seleccione según el objetivo del brief.
          </p>
        </div>

        <div className="user-asset-block">
          <span className="field-label">Tu foto (Design-as-Code)</span>
          <label>
            Subir imagen base
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={loading || uploading}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setError(null);
                setUploading(true);
                try {
                  const up = await uploadAsset(file);
                  setUserAssetUrl(up.url);
                  setUserAssetName(up.filename);
                } catch (err) {
                  setError(err.message);
                  setUserAssetUrl("");
                  setUserAssetName("");
                } finally {
                  setUploading(false);
                }
              }}
            />
            {uploading && <span className="spinner spinner-dark" style={{ marginLeft: "0.5rem" }}></span>}
          </label>
          {userAssetUrl && (
            <p className="hint">
              Foto cargada: <code>{userAssetName || userAssetUrl}</code>
              {" "}
              <button type="button" onClick={() => { setUserAssetUrl(""); setUserAssetName(""); setAlterImageWithAi(false); }}>
                Quitar
              </button>
            </p>
          )}
          <label style={{ display: "block", marginTop: "0.5rem" }}>
            <input
              type="checkbox"
              checked={alterImageWithAi}
              disabled={!userAssetUrl || loading}
              onChange={(e) => setAlterImageWithAi(e.target.checked)}
            />
            {" "}Alterar imagen con IA (requiere prompt; pasa por pending_approval)
          </label>
          {alterImageWithAi && userAssetUrl && (
            <label>
              Indicaciones visuales
              <textarea
                rows={2}
                placeholder="Ej: expandir fondo con nieve, estilo ilustración suave..."
                value={visualInstructions}
                onChange={(e) => setVisualInstructions(e.target.value)}
              />
            </label>
          )}
          <p className="hint">
            Sin IA: tu foto queda intacta como capa base; Pillow añade texto y diseño editorial.
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
          <button disabled={loading || uploading} onClick={() => createAndRun(false)}>
            {loading && contentFormat !== "reel" ? <span className="spinner"></span> : null}
            Ejecutar Sync
          </button>
          <button disabled={loading || uploading} onClick={() => createAndRun(true)}>
            {loading ? <span className="spinner"></span> : null}
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
              {result.result.design.design_source && (
                <> · fuente: {result.result.design.design_source}</>
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
        {result?.result?.design?.video_url && (
          <div style={{ marginBottom: "1rem" }}>
            <p style={{ fontSize: "0.85rem", color: "#888", marginBottom: "0.4rem" }}>
              Reel generado
              {result.result.design.video_provider && (
                <> — <code>{result.result.design.video_provider}</code></>
              )}
              {result.result.design.width > 0 && (
                <> · {result.result.design.width}×{result.result.design.height}px</>
              )}
              {result.result.design.duration_s > 0 && (
                <> · {result.result.design.duration_s.toFixed(1)}s</>
              )}
              :
            </p>
            <video
              controls
              src={resolveImageUrl(result.result.design.video_url)}
              style={{ maxWidth: "100%", borderRadius: "6px", border: "1px solid #333" }}
            />
          </div>
        )}
        {(result?.result?.design?.image_url || result?.result?.design?.video_url) && (
          <div className="revision-block" style={{ marginBottom: "1rem" }}>
            <label>
              Modificaciones a la pieza
              <textarea
                rows={3}
                placeholder="Ej: cambia el headline, fondo más oscuro, CTA más corto…"
                value={revisionNotes}
                onChange={(e) => {
                  setRevisionNotes(e.target.value);
                  if (revisionFeedback && revisionFeedback.runId == null) setRevisionFeedback(null);
                }}
              />
            </label>
            <div className="actions" style={{ marginTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => requestRevision(result?.run_id ?? null, revisionNotes)}
              >
                Solicitar cambios
              </button>
            </div>
            {revisionFeedback && revisionFeedback.runId == null && (
              <p
                className="hint"
                style={{ color: revisionFeedback.ok ? "#2f6f4e" : "#b00020", marginTop: "0.4rem" }}
              >
                {revisionFeedback.message}
              </p>
            )}
            <p className="hint">
              Describe los cambios deseados. La regeneración automática se conectará al pipeline más adelante.
            </p>
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
                <div style={{ marginTop: "0.5rem", marginLeft: 0 }}>
                  <span>
                    <button
                      disabled={approvingRunId != null}
                      onClick={() => doApprove(item.run_id)}
                      style={{ marginRight: "0.3rem" }}
                    >
                      {approvingRunId === item.run_id ? <span className="spinner"></span> : null}
                      {approvingRunId === item.run_id ? "Publicando…" : "✓ Aprobar"}
                    </button>
                    <button disabled={approvingRunId != null} onClick={() => doReject(item.run_id)}>✗ Rechazar</button>
                  </span>
                  <label style={{ display: "block", marginTop: "0.5rem" }}>
                    Modificaciones a la pieza
                    <textarea
                      rows={2}
                      placeholder="Ej: cambia el headline, fondo más oscuro, CTA más corto…"
                      value={revisionByRunId[item.run_id] || ""}
                      onChange={(e) => {
                        const value = e.target.value;
                        setRevisionByRunId((prev) => ({ ...prev, [item.run_id]: value }));
                        if (revisionFeedback?.runId === item.run_id) setRevisionFeedback(null);
                      }}
                    />
                  </label>
                  <div className="actions" style={{ marginTop: "0.35rem" }}>
                    <button
                      type="button"
                      disabled={approvingRunId != null}
                      onClick={() => requestRevision(item.run_id, revisionByRunId[item.run_id] || "")}
                    >
                      Solicitar cambios
                    </button>
                  </div>
                  {revisionFeedback?.runId === item.run_id && (
                    <p
                      className="hint"
                      style={{
                        color: revisionFeedback.ok ? "#2f6f4e" : "#b00020",
                        marginTop: "0.35rem",
                      }}
                    >
                      {revisionFeedback.message}
                    </p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
