import { useCallback, useEffect, useState } from "react";

/**
 * Bandeja de DMs (Instagram / Messenger): quién escribe a las cuentas conectadas y con qué motivo.
 * El agente responde solo en las cuentas con el interruptor activo; se puede pausar por conversación
 * o responder a mano (eso pausa al agente en esa conversación).
 */

const API_BASE = (() => {
  const explicit = import.meta.env.VITE_API_URL;
  if (explicit === "" || explicit === "/") return "/api";
  if (explicit) return String(explicit).replace(/\/$/, "") + "/api";
  return "/api";
})();

const POLL_MS = 20000;

const STATUS_LABELS = {
  nuevo: "Nuevo",
  en_conversacion: "En conversación",
  datos_completos: "Datos completos",
  requiere_humano: "Requiere humano",
  cerrado: "Cerrado",
};

const STATUS_COLORS = {
  nuevo: "#1a6fff",
  en_conversacion: "#f59e0b",
  datos_completos: "#16a34a",
  requiere_humano: "#e11d48",
  cerrado: "#6b7280",
};

const CATEGORY_LABELS = {
  compra: "Compra",
  cotizacion: "Cotización",
  soporte: "Soporte",
  queja: "Queja",
  colaboracion: "Colaboración",
  informacion: "Información",
  otro: "Otro",
};

const PLATFORM_LABELS = { instagram: "Instagram", messenger: "Messenger" };

async function apiFetch(path, apiKey, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const raw = await res.text();
    let detail = raw;
    try {
      detail = JSON.parse(raw).detail || raw;
    } catch {
      /* texto plano */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString();
}

function StatusBadge({ status }) {
  return (
    <span className="inbox-badge" style={{ "--chip": STATUS_COLORS[status] || "#6b7280" }}>
      <span className="inbox-light" aria-hidden="true" />
      {STATUS_LABELS[status] || status}
    </span>
  );
}

const inputStyle = {
  background: "#1a1a2e",
  color: "#eee",
  border: "1px solid #444",
  borderRadius: "4px",
  padding: "4px 8px",
  fontSize: "0.8rem",
};

const ghostButton = {
  background: "transparent",
  border: "1px solid #666",
  color: "#ddd",
  padding: "4px 10px",
  borderRadius: "4px",
  cursor: "pointer",
  fontSize: "0.8rem",
};

function buildQuery(filters) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== "" && v != null) params.set(k, v);
  });
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

function ConversationDetail({ apiKey, contactId, onChanged, onClose }) {
  const [contact, setContact] = useState(null);
  const [reply, setReply] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch(`/inbox/contacts/${contactId}`, apiKey);
      setContact(data);
      setNotes((prev) => (prev === "" ? data.notes || "" : prev));
    } catch (e) {
      setError(e.message);
    }
  }, [apiKey, contactId]);

  useEffect(() => {
    setContact(null);
    setNotes("");
    setReply("");
    setError(null);
    load();
    const id = setInterval(() => {
      if (!document.hidden) load();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const patch = async (body) => {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/inbox/contacts/${contactId}`, apiKey, "PATCH", body);
      await load();
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const sendReply = async () => {
    const text = reply.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/inbox/contacts/${contactId}/reply`, apiKey, "POST", { text });
      setReply("");
      await load();
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!contact) {
    return <div style={{ padding: "1rem", color: "#888" }}>{error || "Cargando conversación..."}</div>;
  }

  const name = contact.full_name || contact.display_name || "Sin nombre";

  return (
    <div style={{ border: "1px solid #333", borderRadius: "8px", padding: "0.75rem", background: "#14141f" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <div>
          <strong>{name}</strong>{" "}
          <span style={{ color: "#888", fontSize: "0.8rem" }}>
            {PLATFORM_LABELS[contact.platform] || contact.platform} · {contact.account_name || "cuenta"}
          </span>
        </div>
        <button onClick={onClose} style={ghostButton}>Cerrar</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.4rem", margin: "0.6rem 0", fontSize: "0.8rem" }}>
        <div><span style={{ color: "#888" }}>Teléfono:</span> {contact.phone || "—"}</div>
        <div><span style={{ color: "#888" }}>Ciudad/Barrio:</span> {contact.city || "—"}</div>
        <div><span style={{ color: "#888" }}>Categoría:</span> {CATEGORY_LABELS[contact.motive_category] || "—"}</div>
        <div><StatusBadge status={contact.status} /></div>
      </div>
      {contact.motive && <p style={{ fontSize: "0.8rem", margin: "0.3rem 0" }}><span style={{ color: "#888" }}>Motivo:</span> {contact.motive}</p>}
      {contact.summary && <p style={{ fontSize: "0.8rem", margin: "0.3rem 0", color: "#bbb" }}><span style={{ color: "#888" }}>Resumen:</span> {contact.summary}</p>}

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", margin: "0.6rem 0" }}>
        {contact.bot_paused ? (
          <button disabled={busy} onClick={() => patch({ bot_paused: false })} style={{ ...ghostButton, borderColor: "#3c3", color: "#3c3" }}>
            Reanudar agente
          </button>
        ) : (
          <button disabled={busy} onClick={() => patch({ bot_paused: true })} style={{ ...ghostButton, borderColor: "#e9a13b", color: "#e9a13b" }}>
            Pausar agente
          </button>
        )}
        <select
          value={contact.status}
          disabled={busy}
          onChange={(e) => patch({ status: e.target.value })}
          style={inputStyle}
        >
          {Object.entries(STATUS_LABELS).map(([k, label]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
      </div>

      <div
        style={{
          maxHeight: "320px",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "0.35rem",
          padding: "0.5rem",
          background: "#0f0f18",
          borderRadius: "6px",
        }}
      >
        {contact.messages.map((m) => {
          const incoming = m.direction === "in";
          return (
            <div key={m.id} style={{ alignSelf: incoming ? "flex-start" : "flex-end", maxWidth: "78%" }}>
              <div
                style={{
                  background: incoming ? "#2a2a3d" : m.sent_by === "human" ? "#1f5f3a" : "#1d4f91",
                  color: "#eee",
                  padding: "0.4rem 0.65rem",
                  borderRadius: "12px",
                  fontSize: "0.82rem",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {m.text}
              </div>
              <div style={{ fontSize: "0.65rem", color: "#777", textAlign: incoming ? "left" : "right" }}>
                {incoming ? "Persona" : m.sent_by === "human" ? "Equipo" : "Agente"} · {formatDate(m.created_at)}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: "0.6rem" }}>
        {contact.can_reply ? (
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Responder como el equipo (pausa al agente en esta conversación)"
              maxLength={900}
              rows={2}
              style={{ ...inputStyle, flex: 1, resize: "vertical" }}
            />
            <button disabled={busy || !reply.trim()} onClick={sendReply} style={{ ...ghostButton, background: "#1877f2", border: "none", color: "#fff" }}>
              Enviar
            </button>
          </div>
        ) : (
          <p style={{ fontSize: "0.75rem", color: "#888", margin: 0 }}>
            Pasaron más de 24 h desde el último mensaje de la persona: Meta no permite responder desde aquí.
          </p>
        )}
      </div>

      <div style={{ marginTop: "0.6rem", display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notas internas del equipo"
          rows={2}
          maxLength={4000}
          style={{ ...inputStyle, flex: 1, resize: "vertical" }}
        />
        <button disabled={busy} onClick={() => patch({ notes })} style={ghostButton}>Guardar nota</button>
      </div>

      {error && <p style={{ color: "#f88", fontSize: "0.8rem", whiteSpace: "pre-wrap" }}>{error}</p>}
    </div>
  );
}

export default function InboxPanel({ apiKey, accountsVersion = 0 }) {
  const [accounts, setAccounts] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState({});
  const [filters, setFilters] = useState({ account_id: "", status: "", category: "", q: "" });
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadAccounts = useCallback(async () => {
    if (!apiKey) return;
    try {
      const data = await apiFetch("/inbox/accounts", apiKey);
      setAccounts(data.items || []);
    } catch (e) {
      setError(e.message);
    }
  }, [apiKey]);

  const loadContacts = useCallback(async () => {
    if (!apiKey) return;
    setLoading(true);
    try {
      const data = await apiFetch(`/inbox/contacts${buildQuery({ ...filters, limit: 100 })}`, apiKey);
      setContacts(data.items || []);
      setTotal(data.total || 0);
      setCounts(data.counts_by_status || {});
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [apiKey, filters]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts, accountsVersion]);

  useEffect(() => {
    const id = setTimeout(() => setFilters((f) => (f.q === search ? f : { ...f, q: search })), 400);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    loadContacts();
    const id = setInterval(() => {
      if (!document.hidden) loadContacts();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [loadContacts]);

  const toggleAgent = async (account) => {
    setError(null);
    setNotice(null);
    try {
      const res = await apiFetch(`/inbox/accounts/${account.id}`, apiKey, "PATCH", {
        dm_agent_enabled: !account.dm_agent_enabled,
      });
      if (res.dm_agent_enabled && res.webhook_subscribed === false) {
        setNotice(
          `Agente activado en ${account.account_name || "la cuenta"}, pero Meta no aceptó la suscripción a mensajes. ` +
            "Reconecta la cuenta Meta para conceder los permisos de mensajería."
        );
      }
      await loadAccounts();
    } catch (e) {
      setError(e.message);
    }
  };

  const downloadCsv = async () => {
    setError(null);
    try {
      const headers = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
      const { account_id, status, category, q } = filters;
      const res = await fetch(`${API_BASE}/inbox/contacts.csv${buildQuery({ account_id, status, category, q })}`, { headers });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `contactos-dm-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    }
  };

  const setFilter = (key) => (e) => setFilters((f) => ({ ...f, [key]: e.target.value }));

  return (
    <section className="card">
      <h2>Bandeja de DMs</h2>
      <p style={{ fontSize: "0.85rem", color: "#888" }}>
        Personas que escriben por Instagram y Messenger a tus cuentas conectadas, sus datos y el motivo del mensaje.
        El agente responde con tono cercano, pide nombre, teléfono y ciudad, y pasa la conversación a tu equipo cuando hace falta.
      </p>

      {error && (
        <pre style={{ color: "#f88", fontSize: "0.8rem", whiteSpace: "pre-wrap", background: "#2a1515", padding: "0.75rem", borderRadius: "6px" }}>
          {error}
        </pre>
      )}
      {notice && <p style={{ color: "#e9a13b", fontSize: "0.8rem" }}>{notice}</p>}

      {accounts.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "#888" }}>
          Conecta una cuenta Meta (Instagram/Facebook) en Integraciones para recibir DMs aquí.
        </p>
      ) : (
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
          {accounts.map((a) => (
            <label
              key={a.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                border: "1px solid #333",
                borderRadius: "8px",
                padding: "0.4rem 0.7rem",
                fontSize: "0.82rem",
                cursor: "pointer",
              }}
              title={a.has_page ? "" : "Esta cuenta no tiene Fan Page asociada: el agente no puede responder"}
            >
              <input type="checkbox" checked={a.dm_agent_enabled} onChange={() => toggleAgent(a)} />
              {a.profile_picture_url && (
                <img src={a.profile_picture_url} alt="" style={{ width: 20, height: 20, borderRadius: "50%", objectFit: "cover" }} />
              )}
              <span>{a.account_name || `Cuenta ${a.id}`}</span>
              <span style={{ color: a.dm_agent_enabled ? "#3c3" : "#888" }}>
                {a.dm_agent_enabled ? "Agente activo" : "Agente apagado"}
              </span>
              <span style={{ color: "#777" }}>· {a.contacts} contactos</span>
            </label>
          ))}
        </div>
      )}

      <div className="inbox-chips">
        {Object.entries(STATUS_LABELS).map(([k, label]) => {
          const count = counts[k] || 0;
          const classes = ["inbox-chip", filters.status === k && "is-active", count > 0 && "has-items"]
            .filter(Boolean)
            .join(" ");
          return (
            <button
              key={k}
              className={classes}
              style={{ "--chip": STATUS_COLORS[k] }}
              aria-pressed={filters.status === k}
              onClick={() => setFilters((f) => ({ ...f, status: f.status === k ? "" : k }))}
            >
              <span className="inbox-light" aria-hidden="true" />
              {label}
              <span className="inbox-chip-count">{count}</span>
            </button>
          );
        })}
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem", alignItems: "center" }}>
        <select value={filters.account_id} onChange={setFilter("account_id")} style={inputStyle}>
          <option value="">Todas las cuentas</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.account_name || `Cuenta ${a.id}`}</option>
          ))}
        </select>
        <select value={filters.category} onChange={setFilter("category")} style={inputStyle}>
          <option value="">Todos los motivos</option>
          {Object.entries(CATEGORY_LABELS).map(([k, label]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar nombre, teléfono, ciudad, motivo"
          style={{ ...inputStyle, minWidth: "220px" }}
        />
        <button className="inbox-btn" onClick={loadContacts} disabled={loading}>{loading ? "..." : "Refrescar"}</button>
        <button className="inbox-btn" onClick={downloadCsv}>Exportar CSV</button>
        <span style={{ fontSize: "0.9rem", color: "var(--brand-muted)", fontWeight: 600 }}>{total} conversaciones</span>
      </div>

      {contacts.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "#888" }}>Aún no hay conversaciones con estos filtros.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ fontSize: "0.8rem", borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #444" }}>
                <th style={{ padding: "4px 8px" }}>Persona</th>
                <th style={{ padding: "4px 8px" }}>Teléfono</th>
                <th style={{ padding: "4px 8px" }}>Ciudad/Barrio</th>
                <th style={{ padding: "4px 8px" }}>Motivo</th>
                <th style={{ padding: "4px 8px" }}>Estado</th>
                <th style={{ padding: "4px 8px" }}>Red</th>
                <th style={{ padding: "4px 8px" }}>Último mensaje</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => setSelectedId(c.id === selectedId ? null : c.id)}
                  style={{
                    cursor: "pointer",
                    borderBottom: "1px solid #222",
                    background: c.id === selectedId ? "#1d1d2e" : "transparent",
                  }}
                >
                  <td style={{ padding: "4px 8px" }}>
                    {c.full_name || c.display_name || "Sin nombre"}
                    {c.bot_paused && <span title="Agente pausado" style={{ marginLeft: 6, color: "#e9a13b" }}>⏸</span>}
                  </td>
                  <td style={{ padding: "4px 8px" }}>{c.phone || "—"}</td>
                  <td style={{ padding: "4px 8px" }}>{c.city || "—"}</td>
                  <td style={{ padding: "4px 8px", maxWidth: "280px" }}>
                    {c.motive_category && <code style={{ marginRight: 6 }}>{CATEGORY_LABELS[c.motive_category] || c.motive_category}</code>}
                    <span style={{ color: "var(--brand-muted)" }}>{c.motive || "—"}</span>
                  </td>
                  <td style={{ padding: "4px 8px" }}><StatusBadge status={c.status} /></td>
                  <td style={{ padding: "4px 8px" }}>{PLATFORM_LABELS[c.platform] || c.platform}</td>
                  <td style={{ padding: "4px 8px", color: "#888" }}>{formatDate(c.last_message_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedId && (
        <div style={{ marginTop: "0.75rem" }}>
          <ConversationDetail
            apiKey={apiKey}
            contactId={selectedId}
            onChanged={loadContacts}
            onClose={() => setSelectedId(null)}
          />
        </div>
      )}
    </section>
  );
}
