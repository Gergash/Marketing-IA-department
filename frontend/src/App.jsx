import { useEffect, useState } from "react";

/** En dev: rutas relativas /api → proxy de Vite a FastAPI. En prod o override: VITE_API_URL (sin /api final). */
function apiOrigin() {
  const explicit = import.meta.env.VITE_API_URL;
  if (explicit) return String(explicit).replace(/\/$/, "");
  if (import.meta.env.DEV) return "";
  return "http://localhost:8000";
}

const API_BASE = `${apiOrigin()}/api`;

async function api(path, method = "GET", body = null, role = "admin") {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Role": role,
      "X-Tenant-Id": "demo-tenant"
    },
    body: body ? JSON.stringify(body) : undefined
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export default function App() {
  const [form, setForm] = useState({
    tema: "",
    publico_objetivo: "",
    red_social: "linkedin",
    objetivo: "branding",
    tono_marca: "profesional y cercano"
  });
  const [history, setHistory] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadHistory = async () => {
    const items = await api("/runs", "GET", null, "viewer");
    setHistory(items);
  };

  useEffect(() => {
    loadHistory().catch(console.error);
  }, []);

  const createAndRun = async (asyncMode = false) => {
    setLoading(true);
    try {
      const brief = await api("/briefs", "POST", form, "editor");
      const runReq = {
        brief_id: brief.id,
        publish: true,
        requires_approval: false,
        idempotency_key: `${brief.id}-${Date.now()}`
      };
      const run = await api(asyncMode ? "/runs/async" : "/runs/sync", "POST", runReq, "editor");
      if (!asyncMode) setResult(run.result);
      if (asyncMode) {
        setResult({ queued_run_id: run.run_id, status: run.status });
      }
      await loadHistory();
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container">
      <h1>Marketing DEPA IA - MVP Dashboard</h1>
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
          <button disabled={loading} onClick={() => createAndRun(false)}>Ejecutar Sync</button>
          <button disabled={loading} onClick={() => createAndRun(true)}>Enviar Async</button>
        </div>
      </section>

      <section className="card">
        <h2>Resultado</h2>
        <pre>{result ? JSON.stringify(result, null, 2) : "Sin ejecucion sincronica aun."}</pre>
      </section>

      <section className="card">
        <h2>Historial de ejecuciones</h2>
        <ul>
          {history.map((item) => (
            <li key={item.run_id}>
              #{item.run_id} - {item.status}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
