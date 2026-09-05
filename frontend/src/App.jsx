import { useEffect, useState } from "react";
import AdvisorChatBubble from "./AdvisorChatBubble";
import AgentThoughtThread from "./AgentThoughtThread";
import Integrations from "./Integrations";
import { BrandMark } from "./BrandMark";
import { getAuthToken } from "./auth";

/** Traza del hilo de pensamiento: el cliente la genera porque /runs/sync no devuelve el run_id hasta terminar. */
function newTraceId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().replace(/-/g, "");
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

const RUN_IN_PROGRESS = ["queued", "running", "publishing"];

const FORM_LABELS = {
  tema: "Descripción del producto o evento",
  publico_objetivo: "Público objetivo",
  red_social: "Red social",
  objetivo: "Objetivo",
  tono_marca: "Tono de marca",
};

const FORM_PLACEHOLDERS = {
  tema: "Ej: Lanzamiento del coworking en Siete Vueltas / curso de IA para pymes…",
  publico_objetivo: "Ej: dueños de negocio en la región…",
  red_social: "instagram",
  objetivo: "branding | leads | comunidad…",
  tono_marca: "profesional y cercano",
};

// Espejo de agents/marketing_agents/image_specs.py — solo se usa si GET /image/formats falla.
const FALLBACK_NETWORKS = [
  { id: "instagram", label: "Instagram" },
  { id: "facebook", label: "Facebook" },
  { id: "linkedin", label: "LinkedIn" },
  { id: "tiktok", label: "TikTok" },
  { id: "x", label: "X (Twitter)" },
];

const FALLBACK_FORMATS = {
  instagram: [
    { id: "feed", label: "Post en feed", width: 1080, height: 1350, is_video: false },
    { id: "story", label: "Historia (vertical)", width: 1080, height: 1920, is_video: false },
    { id: "reel", label: "Reel — video generado con IA", width: 1080, height: 1920, is_video: true },
    { id: "user_clip_reel", label: "Video con mis clips (Drive)", width: 1080, height: 1920, is_video: true },
    { id: "universal", label: "Universal — encaja en todas las redes", width: 1080, height: 1080, is_video: false },
  ],
  facebook: [
    { id: "feed", label: "Post en feed", width: 1080, height: 1350, is_video: false },
    { id: "story", label: "Historia (vertical)", width: 1080, height: 1920, is_video: false },
    { id: "reel", label: "Reel — video generado con IA", width: 1080, height: 1920, is_video: true },
    { id: "user_clip_reel", label: "Video con mis clips (Drive)", width: 1080, height: 1920, is_video: true },
    { id: "universal", label: "Universal — encaja en todas las redes", width: 1080, height: 1080, is_video: false },
  ],
  linkedin: [
    { id: "feed", label: "Post en feed", width: 1200, height: 627, is_video: false },
    { id: "universal", label: "Universal — encaja en todas las redes", width: 1080, height: 1080, is_video: false },
  ],
  tiktok: [
    { id: "story", label: "Historia (vertical)", width: 1080, height: 1920, is_video: false },
    { id: "reel", label: "Reel — video generado con IA", width: 1080, height: 1920, is_video: true },
    { id: "user_clip_reel", label: "Video con mis clips (Drive)", width: 1080, height: 1920, is_video: true },
    { id: "universal", label: "Universal — encaja en todas las redes", width: 1080, height: 1080, is_video: false },
  ],
  x: [
    { id: "feed", label: "Post en feed", width: 1200, height: 675, is_video: false },
    { id: "reel", label: "Reel — video generado con IA", width: 1080, height: 1920, is_video: true },
    { id: "universal", label: "Universal — encaja en todas las redes", width: 1080, height: 1080, is_video: false },
  ],
};

// ---------------------------------------------------------------------------
// API key — almacenada en sessionStorage (no persiste entre sesiones)
// ---------------------------------------------------------------------------
function getApiKey() {
  return getAuthToken();
}

function saveApiKey(key) {
  sessionStorage.setItem("api_key", key);
}

// ---------------------------------------------------------------------------
// Cliente HTTP base
// ---------------------------------------------------------------------------
function apiOrigin() {
  const explicit = import.meta.env.VITE_API_URL;
  // "" o unset en build prod (Caddy same-origin) → rutas relativas /api
  if (explicit === "" || explicit === "/") return "";
  if (explicit) return String(explicit).replace(/\/$/, "");
  if (import.meta.env.DEV) return "";
  return "";
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

async function uploadBrandManual(file) {
  const headers = {};
  const key = getApiKey();
  if (key) headers["Authorization"] = `Bearer ${key}`;
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_BASE}/briefs/upload-brand-manual`, {
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
  const [socialAccounts, setSocialAccounts] = useState([]);
  const [socialAccountId, setSocialAccountId] = useState("");
  const [contentFormat, setContentFormat] = useState("feed");
  const [networks, setNetworks] = useState(FALLBACK_NETWORKS);
  const [formatsByNetwork, setFormatsByNetwork] = useState(FALLBACK_FORMATS);
  const [imageProvider, setImageProvider] = useState("venice");
  const [imageProviders, setImageProviders] = useState([]);
  const [videoGenMode, setVideoGenMode] = useState("scenes");
  const [veniceVideoModel, setVeniceVideoModel] = useState("seedance-2.0");
  const [videoModes, setVideoModes] = useState([]);
  const [videoModels, setVideoModels] = useState([]);
  const [veniceConfigured, setVeniceConfigured] = useState(false);
  const [archetypeOverride, setArchetypeOverride] = useState("");
  const [archetypes, setArchetypes] = useState([]);
  const [userAssetUrl, setUserAssetUrl] = useState("");
  const [userAssetName, setUserAssetName] = useState("");
  const [brandManual, setBrandManual] = useState(null);
  const [uploadingBrand, setUploadingBrand] = useState(false);
  const [driveFolderId, setDriveFolderId] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [ctaOnImage, setCtaOnImage] = useState(false);
  const [alterImageWithAi, setAlterImageWithAi] = useState(false);
  const [visualInstructions, setVisualInstructions] = useState("");
  const [traceId, setTraceId] = useState(null);
  const [interactive, setInteractive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [approvingRunId, setApprovingRunId] = useState(null);
  const [revisingRunId, setRevisingRunId] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  // Notas de revisión que se envían a POST /runs/{id}/revise para regenerar la pieza
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

  const loadSocialAccounts = async () => {
    try {
      const data = await api("/auth/accounts");
      setSocialAccounts(Array.isArray(data.accounts) ? data.accounts : []);
    } catch {
      setSocialAccounts([]);
    }
  };

  const loadContentFormats = async () => {
    try {
      const data = await api("/image/formats");
      if (Array.isArray(data.networks) && data.networks.length > 0) setNetworks(data.networks);
      if (data.formats_by_network && Object.keys(data.formats_by_network).length > 0) {
        setFormatsByNetwork(data.formats_by_network);
      }
    } catch {
      setNetworks(FALLBACK_NETWORKS);
      setFormatsByNetwork(FALLBACK_FORMATS);
    }
  };

  const currentNetwork = (form.red_social || "instagram").toLowerCase();
  const availableFormats =
    formatsByNetwork[currentNetwork] || formatsByNetwork.instagram || FALLBACK_FORMATS.instagram;

  // Cambiar de red puede dejar seleccionado un formato inexistente (p. ej. story en LinkedIn)
  useEffect(() => {
    if (!availableFormats.some((f) => f.id === contentFormat)) {
      setContentFormat(availableFormats[0]?.id || "feed");
    }
  }, [currentNetwork, formatsByNetwork]);

  // red_social del brief → provider de oauth_tokens
  const providerForNetwork = (network) =>
    ({
      instagram: "meta",
      ig: "meta",
      facebook: "meta",
      linkedin: "linkedin",
      x: "x",
      twitter: "x",
    }[(network || "").toLowerCase()] || null);

  const providerShortLabel = (provider) =>
    ({ meta: "IG", linkedin: "LinkedIn", google: "Drive", x: "X" }[provider] || provider);

  /** Etiqueta legible: "Negocio 1 — IG", "Mi página — LinkedIn" */
  const formatAccountLabel = (account) => {
    const name = account.account_name || account.account_id || `Cuenta #${account.id}`;
    return `${name} — ${providerShortLabel(account.provider)}`;
  };

  const accountsForNetwork = socialAccounts.filter(
    (a) => a.provider === providerForNetwork(form.red_social)
  );

  // Preselección: única cuenta del proveedor → elegida automáticamente
  useEffect(() => {
    const stillValid = accountsForNetwork.some((a) => String(a.id) === socialAccountId);
    if (!stillValid) {
      setSocialAccountId(accountsForNetwork.length === 1 ? String(accountsForNetwork[0].id) : "");
    }
  }, [form.red_social, socialAccounts]);

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
        { id: "venice", label: "Venice.ai" },
      ]);
    }
  };

  const loadVideoOptions = async () => {
    try {
      const data = await api("/video/options");
      setVideoModes(Array.isArray(data.modes) ? data.modes : []);
      setVideoModels(Array.isArray(data.models) ? data.models : []);
      setVeniceConfigured(Boolean(data.venice_configured));
      if (data.default_mode) setVideoGenMode(data.default_mode);
      if (data.default_model) setVeniceVideoModel(data.default_model);
    } catch {
      setVideoModes([
        { id: "full", label: "Clip AI completo (Venice)" },
        { id: "scenes", label: "Unir tomas AI (Venice + Shotstack)" },
        { id: "still", label: "Stills + Ken Burns" },
      ]);
      setVideoModels([
        { id: "seedance-2.5", label: "Seedance 2.5" },
        { id: "seedance-2.0", label: "Seedance 2.0" },
        { id: "kling-o3", label: "Kling O3" },
        { id: "minimax-h3", label: "MiniMax H3" },
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

  const loadBrandManual = async () => {
    try {
      const data = await api("/briefs/brand-manual");
      setBrandManual(data || null);
    } catch {
      setBrandManual(null);
    }
  };

  useEffect(() => {
    loadHistory();
    loadSocialStatus();
    loadSocialAccounts();
    loadImageProviders();
    loadContentFormats();
    loadVideoOptions();
    loadArchetypes();
    loadBrandManual();
  }, [apiKey]);

  // Poll de runs async (reels): rellena Resultado cuando pasa a pending_approval con video_url
  useEffect(() => {
    const runId = result?.run_id;
    const status = result?.status;
    if (!runId) return undefined;
    const done = ["pending_approval", "completed", "failed", "rejected", "deduplicated"];
    if (done.includes(status) && result?.result) return undefined;
    if (!["queued", "running", "publishing"].includes(status) && result?.result) return undefined;

    let cancelled = false;
    const tick = async () => {
      try {
        const updated = await api(`/runs/${runId}`);
        if (cancelled) return;
        setResult({
          run_id: updated.run_id,
          status: updated.status,
          result: updated.result,
          error_message: updated.error_message,
        });
        if (done.includes(updated.status)) {
          await loadHistory();
        }
      } catch {
        /* ignore transient poll errors */
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [result?.run_id, result?.status]);

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
    setError(null);

    // Con cuentas conectadas para la red del brief, hay que elegir una antes del POST
    if (accountsForNetwork.length > 0 && !socialAccountId) {
      setError(
        `Elige la cuenta destino (${providerShortLabel(providerForNetwork(form.red_social)) || form.red_social}) antes de ejecutar el run.`
      );
      return;
    }

    const trace = newTraceId();
    setTraceId(trace);
    setLoading(true);
    try {
      const brief = await api("/briefs", "POST", form);
      const runReq = {
        trace_id: trace,
        interactive,
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
        ...(contentFormat === "reel"
          ? { video_gen_mode: videoGenMode, venice_video_model: veniceVideoModel }
          : {}),
        ...(socialAccountId ? { social_account_id: Number(socialAccountId) } : {}),
        ...(linkUrl.trim() ? { link_url: linkUrl.trim() } : {}),
        ...(ctaOnImage ? { cta_on_image: true } : {}),
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
      setResult({
        run_id: updated.run_id,
        status: updated.status,
        result: updated.result,
        error_message: updated.error_message,
      });
      await loadHistory();
    } catch (e) {
      setError(e.message);
      try {
        const updated = await api(`/runs/${runId}`);
        if (updated?.error_message) {
          setError(`${e.message}\n\n${updated.error_message}`);
        }
      } catch {
        /* keep original */
      }
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

  /** Regenera la pieza del run aplicando las notas del revisor (POST /runs/{id}/revise). */
  const requestRevision = async (runId, notes) => {
    const trimmed = (notes || "").trim();
    if (!trimmed) {
      setRevisionFeedback({
        runId: runId ?? null,
        ok: false,
        message: "Escribe qué quieres cambiar en la pieza antes de solicitar cambios.",
      });
      return;
    }
    if (runId == null) {
      setRevisionFeedback({
        runId: null,
        ok: false,
        message: "No hay un run asociado a esta pieza todavía.",
      });
      return;
    }
    if (revisingRunId != null) return;

    const trace = newTraceId();
    setTraceId(trace);
    setRevisingRunId(runId);
    setError(null);
    setRevisionFeedback({ runId, ok: true, message: "Regenerando la pieza con tus notas…" });
    try {
      const response = await api(`/runs/${runId}/revise`, "POST", {
        notes: trimmed,
        revised_by: "human",
        trace_id: trace,
        interactive,
      });
      // Los reels se re-renderizan en la cola video_render: el resultado no viene en la respuesta.
      if (response.status === "queued") {
        setRevisionFeedback({
          runId,
          ok: true,
          message: "Revisión encolada; el video se está re-renderizando (puede tardar minutos).",
        });
      } else {
        const updated = await api(`/runs/${runId}`);
        setResult({ run_id: updated.run_id, status: updated.status, result: updated.result });
        setRevisionFeedback({
          runId,
          ok: true,
          message: "Pieza regenerada; revísala y aprueba si te convence.",
        });
      }
      setRevisionByRunId((prev) => ({ ...prev, [runId]: "" }));
      if (runId === result?.run_id) setRevisionNotes("");
      await loadHistory();
    } catch (e) {
      setRevisionFeedback({ runId, ok: false, message: e.message });
    } finally {
      setRevisingRunId(null);
    }
  };

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <main className="container brand-theme">
      <header className="app-brand-header">
        <BrandMark size={48} to="/" />
        <div>
          <h1>Marketing Agéntico (Auto)</h1>
          <p className="app-brand-sub">Estudio de marketing multiagente</p>
        </div>
      </header>

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
      <Integrations apiKey={apiKey} onAccountsChanged={loadSocialAccounts} />

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
          Red social
          <select
            value={currentNetwork}
            disabled={loading}
            onChange={(e) => setForm((prev) => ({ ...prev, red_social: e.target.value }))}
          >
            {networks.map((n) => (
              <option key={n.id} value={n.id}>{n.label}</option>
            ))}
          </select>
        </label>
        <label>
          Formato de publicación
          <select
            value={contentFormat}
            disabled={loading}
            onChange={(e) => setContentFormat(e.target.value)}
          >
            {availableFormats.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label} ({f.width}×{f.height})
              </option>
            ))}
          </select>
        </label>
        <p className="hint">
          Cada red muestra solo sus formatos válidos; las dimensiones se aplican al generar la pieza.
          {contentFormat === "universal" &&
            " Universal: pieza cuadrada 1080×1080 que entra sin recortes en Instagram, Facebook, LinkedIn y X, y centrada en TikTok — úsala cuando el mismo post va a varias redes."}
          {(contentFormat === "reel" || contentFormat === "user_clip_reel") &&
            " Los reels son async-only: se envían siempre con \"Enviar Async\"."}
        </p>
        <p className="hint">
          La cuenta destino se elige en el brief (debajo), justo antes de Sync/Async.
          {!providerForNetwork(currentNetwork) &&
            ` Publicación automática en ${currentNetwork} aún no implementada: la pieza se genera y queda para descargar/publicar a mano.`}
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
        {contentFormat === "reel" && (
          <div className="video-gen-block" style={{ marginTop: "0.75rem" }}>
            <label>
              Generación de video (Venice AI)
              <select
                value={videoGenMode}
                disabled={loading}
                onChange={(e) => setVideoGenMode(e.target.value)}
              >
                {(videoModes.length > 0
                  ? videoModes
                  : [
                      { id: "full", label: "Clip AI completo" },
                      { id: "scenes", label: "Unir tomas AI" },
                      { id: "still", label: "Stills + Shotstack" },
                    ]
                ).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Modelo de video
              <select
                value={veniceVideoModel}
                disabled={loading || videoGenMode === "still"}
                onChange={(e) => setVeniceVideoModel(e.target.value)}
              >
                {(videoModels.length > 0
                  ? videoModels
                  : [
                      { id: "seedance-2.5", label: "Seedance 2.5" },
                      { id: "seedance-2.0", label: "Seedance 2.0" },
                      { id: "kling-o3", label: "Kling O3" },
                      { id: "minimax-h3", label: "MiniMax H3" },
                    ]
                ).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            <p className="hint">
              {videoGenMode === "full"
                ? "Venice genera un solo clip con Seedance / Kling / MiniMax (no collage de fotos)."
                : videoGenMode === "scenes"
                  ? "Venice anima cada toma y Shotstack las une en el reel final."
                  : "Solo stills con efecto Ken Burns en Shotstack (sin generación de video AI)."}
              {!veniceConfigured && videoGenMode !== "still"
                ? " Aviso: VENICE_API_KEY no configurada en el servidor."
                : ""}
            </p>
          </div>
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
              ? "Flux Pro vía API. Para alterar fotos reales con personas, preferí Venice (gpt-image-2-edit)."
              : imageProvider === "venice"
                ? "Venice.ai + gpt-image-2 / gpt-image-2-edit. Si cambias .env, recarga esta página (settings se re-leen por mtime)."
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
          <span className="field-label">Manual de marca (PDF)</span>
          <label>
            Importar PDF de identidad / brand book
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={loading || uploadingBrand}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setError(null);
                setUploadingBrand(true);
                try {
                  const up = await uploadBrandManual(file);
                  setBrandManual(up);
                } catch (err) {
                  setError(err.message);
                } finally {
                  setUploadingBrand(false);
                  e.target.value = "";
                }
              }}
            />
            {uploadingBrand && <span className="spinner spinner-dark" style={{ marginLeft: "0.5rem" }}></span>}
          </label>
          {brandManual && (
            <p className="hint">
              Activo: <code>{brandManual.original_filename}</code>
              {" "}({brandManual.char_count} caracteres extraídos
              {brandManual.extraction_method ? ` · ${brandManual.extraction_method}` : ""})
              {" "}
              <button
                type="button"
                onClick={async () => {
                  try {
                    await api("/briefs/brand-manual", "DELETE");
                    setBrandManual(null);
                  } catch (err) {
                    setError(err.message);
                  }
                }}
              >
                Quitar
              </button>
            </p>
          )}
          {brandManual?.palette_hex?.length > 0 && (
            <div className="brand-palette" style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap", margin: "0.4rem 0" }}>
              {brandManual.palette_hex.map((hx) => (
                <span
                  key={hx}
                  title={hx}
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: 4,
                    background: hx,
                    border: "1px solid rgba(0,0,0,0.15)",
                  }}
                />
              ))}
              <span className="hint" style={{ alignSelf: "center" }}>
                Paleta detectada ({brandManual.palette_hex.length})
                {brandManual.color_roles?.primary
                  ? ` · primario ${brandManual.color_roles.primary}`
                  : ""}
              </span>
            </div>
          )}
          {(brandManual?.font_names?.length > 0 ||
            brandManual?.layout_hints?.length > 0 ||
            brandManual?.suggested_archetype) && (
            <p className="hint" style={{ margin: "0.35rem 0" }}>
              {brandManual.font_names?.length > 0 && (
                <>Tipografías: {brandManual.font_names.join(", ")}. </>
              )}
              {brandManual.logo_placements?.length > 0 && (
                <>Logo: {brandManual.logo_placements.join(", ")}. </>
              )}
              {brandManual.suggested_archetype && (
                <>Layout sugerido: <code>{brandManual.suggested_archetype}</code>. </>
              )}
              {brandManual.layout_hints?.length > 0 && (
                <>Disposiciones: {brandManual.layout_hints.slice(0, 4).join(" · ")}</>
              )}
            </p>
          )}
          {brandManual?.logo_urls?.length > 0 && (
            <div className="brand-logos" style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", margin: "0.4rem 0", alignItems: "center" }}>
              {brandManual.logo_urls.map((url) => (
                <img
                  key={url}
                  src={url}
                  alt="Logo del manual"
                  style={{
                    maxHeight: 48,
                    maxWidth: 120,
                    objectFit: "contain",
                    background: "#fff",
                    border: "1px solid rgba(0,0,0,0.1)",
                    borderRadius: 4,
                    padding: 4,
                  }}
                />
              ))}
              <span className="hint">Logos reconocidos ({brandManual.logo_urls.length})</span>
            </div>
          )}
          {brandManual?.text_preview && (
            <p className="hint brand-preview">{brandManual.text_preview}</p>
          )}
          <p className="hint">
            Escaneo minucioso del PDF: tipografías y texto (pypdf/PaddleOCR), paleta de color
            de las páginas y logos embebidos/recortados. Todo manda en diseño con prioridad máxima.
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
                  // Foto real del sitio: por defecto activar edición IA (Venice/fal)
                  setAlterImageWithAi(true);
                  setVisualInstructions((prev) =>
                    prev.trim()
                      ? prev
                      : "Agrega dos personas realistas sentadas en las sillas vacías de la mesa, cena natural. No agregues ni modifiques texto."
                  );
                  // Preferir Venice para /image/edit (fal img2img suele deformar tipografía de la foto)
                  setImageProvider((cur) => {
                    const hasVenice = imageProviders.some((p) => p.id === "venice");
                    return hasVenice ? "venice" : cur;
                  });
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
            {" "}Alterar foto real con IA (Venice gpt-image-2-edit / fal) — agrega personas, objetos, etc.
          </label>
          {alterImageWithAi && userAssetUrl && imageProvider === "fal" && (
            <p className="hint" style={{ color: "#b45309" }}>
              Aviso: con fal la IA puede deformar textos ya presentes en la foto. Para editar foto real
              usa <strong>Venice (gpt-image-2)</strong>.
            </p>
          )}
          {alterImageWithAi && userAssetUrl && (
            <label>
              Indicaciones visuales
              <textarea
                rows={2}
                placeholder="Ej: agrega una pareja sentada en las dos sillas, cena romántica realista. No agregues texto."
                value={visualInstructions}
                onChange={(e) => setVisualInstructions(e.target.value)}
              />
            </label>
          )}
          <p className="hint">
            Con IA (recomendado): Venice edita solo la escena (personas/objetos) y Pillow aplica tipografía limpia.
            La IA no debe pintar letras — si ves texto ilegible, el editor recibió copy por error o hay un API viejo en :8000.
            Sin IA: solo se pegan textos sobre la foto (las sillas vacías no cambian).
          </p>
        </div>

        {/* red_social se elige arriba, junto al formato de publicación */}
        {Object.keys(form).filter((key) => key !== "red_social").map((key) => (
          <label key={key}>
            {FORM_LABELS[key] || key}
            {key === "tema" ? (
              <textarea
                rows={3}
                placeholder={FORM_PLACEHOLDERS[key] || ""}
                value={form[key]}
                onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
              />
            ) : (
              <input
                placeholder={FORM_PLACEHOLDERS[key] || ""}
                value={form[key]}
                onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
              />
            )}
          </label>
        ))}

        <label>
          Cuenta destino
          <select
            value={socialAccountId}
            onChange={(e) => setSocialAccountId(e.target.value)}
            disabled={loading || uploading || accountsForNetwork.length === 0}
            required={accountsForNetwork.length > 0}
          >
            {accountsForNetwork.length === 0 ? (
              <option value="">
                Sin cuentas para {form.red_social} — conecta en Integraciones
              </option>
            ) : (
              <>
                <option value="">
                  {accountsForNetwork.length === 1
                    ? "Elige la cuenta…"
                    : `Elige a cuál de las ${accountsForNetwork.length} cuentas publicar…`}
                </option>
                {accountsForNetwork.map((a) => (
                  <option key={a.id} value={String(a.id)}>
                    {formatAccountLabel(a)}
                  </option>
                ))}
              </>
            )}
          </select>
        </label>
        <p className="hint">
          Filtrado por <code>red_social</code> del brief (Instagram/Facebook → Meta/IG,
          LinkedIn → LinkedIn, X → X). Al aprobar, se publica en esta cuenta.
          {(() => {
            const selected = accountsForNetwork.find((a) => String(a.id) === socialAccountId);
            return selected ? ` Seleccionada: ${formatAccountLabel(selected)}.` : "";
          })()}
        </p>

        <label>
          Enlace en la descripción (opcional)
          <input
            type="url"
            placeholder="https://… (se agrega al caption junto con hashtags)"
            value={linkUrl}
            disabled={loading || uploading}
            onChange={(e) => setLinkUrl(e.target.value)}
          />
        </label>
        <p className="hint">
          Links y hashtags van en la descripción del post, no como botón en la imagen.
        </p>
        <label style={{ display: "block", marginTop: "0.5rem" }}>
          <input
            type="checkbox"
            checked={ctaOnImage}
            disabled={loading || uploading}
            onChange={(e) => setCtaOnImage(e.target.checked)}
          />
          {" "}Remarcar CTA en la imagen (solo si hay info importante que destacar; no es el estándar)
        </label>

        <label style={{ display: "block", marginTop: "0.5rem" }}>
          <input
            type="checkbox"
            checked={interactive}
            disabled={loading || uploading}
            onChange={(e) => setInteractive(e.target.checked)}
          />
          {" "}Modo interactivo (los agentes se detienen a preguntarte en estrategia, copy y arte)
        </label>

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

      {/* Hilo de pensamiento de los agentes */}
      <AgentThoughtThread
        api={api}
        traceId={traceId}
        active={
          loading || revisingRunId != null || RUN_IN_PROGRESS.includes(result?.status)
        }
      />

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
                <> · fuente: <code>{result.result.design.design_source}</code></>
              )}
              {result.result.design.design_source === "user_overlay" && (
                <span style={{ color: "#b45309" }}>
                  {" "}(solo overlay — la foto no se editó con IA; marca “Alterar foto real” y Venice)
                </span>
              )}
              {result.result.design.design_source === "user_img2img" && (
                <span style={{ color: "#047857" }}>
                  {" "}(foto editada con IA + tipografía Pillow)
                </span>
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
                  if (revisionFeedback && revisionFeedback.runId === result?.run_id) {
                    setRevisionFeedback(null);
                  }
                }}
              />
            </label>
            <div className="actions" style={{ marginTop: "0.5rem" }}>
              <button
                type="button"
                disabled={revisingRunId != null}
                onClick={() => requestRevision(result?.run_id ?? null, revisionNotes)}
              >
                {revisingRunId === result?.run_id ? <span className="spinner"></span> : null}
                {revisingRunId === result?.run_id ? "Regenerando…" : "Solicitar cambios"}
              </button>
            </div>
            {revisionFeedback && revisionFeedback.runId === result?.run_id && (
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
                  {item.result?.design?.video_url && (
                    <div style={{ marginBottom: "0.75rem" }}>
                      <p className="hint" style={{ marginBottom: "0.35rem" }}>
                        Vista previa del reel (revisa antes de aprobar):
                      </p>
                      <video
                        controls
                        src={resolveImageUrl(item.result.design.video_url)}
                        style={{ maxWidth: "320px", width: "100%", borderRadius: "6px", border: "1px solid #333" }}
                      />
                    </div>
                  )}
                  {item.result?.design?.image_url && !item.result?.design?.video_url && (
                    <div style={{ marginBottom: "0.75rem" }}>
                      <img
                        src={resolveImageUrl(item.result.design.image_url)}
                        alt={`Preview run ${item.run_id}`}
                        style={{ maxWidth: "240px", borderRadius: "6px", border: "1px solid #333" }}
                      />
                    </div>
                  )}
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
                      disabled={approvingRunId != null || revisingRunId != null}
                      onClick={() => requestRevision(item.run_id, revisionByRunId[item.run_id] || "")}
                    >
                      {revisingRunId === item.run_id ? <span className="spinner"></span> : null}
                      {revisingRunId === item.run_id ? "Regenerando…" : "Solicitar cambios"}
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

      <AdvisorChatBubble
        api={api}
        briefContext={{
          tema: form.tema,
          publico_objetivo: form.publico_objetivo,
          red_social: form.red_social,
          objetivo: form.objetivo,
          tono_marca: form.tono_marca,
          content_format: contentFormat,
        }}
      />
    </main>
  );
}
