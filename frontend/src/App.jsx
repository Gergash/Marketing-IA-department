import { useEffect, useState } from "react";

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
    red_social: "linkedin",
    objetivo: "branding",
    tono_marca: "profesional y cercano",
  });
  const [history, setHistory] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadHistory = async () => {
    try {
      const items = await api("/runs");
      setHistory(items);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    loadHistory();
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
    setError(null);
    try {
      await api(`/runs/${runId}/approve`, "POST", { approved_by: "human" });
      await loadHistory();
    } catch (e) {
      setError(e.message);
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

      {/* Formulario */}
      <section className="card">
        <h2>Nuevo Brief</h2>
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
              {item.approved_by && (
                <span style={{ marginLeft: "0.5rem", color: "#888" }}>
                  (por {item.approved_by})
                </span>
              )}
              {item.status === "pending_approval" && (
                <span style={{ marginLeft: "1rem" }}>
                  <button onClick={() => doApprove(item.run_id)} style={{ marginRight: "0.3rem" }}>
                    ✓ Aprobar
                  </button>
                  <button onClick={() => doReject(item.run_id)}>✗ Rechazar</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
