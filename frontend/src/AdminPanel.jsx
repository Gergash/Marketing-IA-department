import { useEffect, useState } from "react";
import { authFetch, isStagingMode } from "./auth";
import { BrandMark } from "./BrandMark";
import { Link } from "./RouterLink";
import "./staging.css";

const COP = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
const NUM = new Intl.NumberFormat("es-CO");

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function useDebounced(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function ShareBars({ items }) {
  if (!items || items.length === 0) {
    return <p className="admin-empty">Sin datos de consumo todavía.</p>;
  }
  return (
    <div>
      {items.map((it) => (
        <div className="admin-bar-row" key={it.provider || it.key}>
          <span>{it.provider || it.label || it.key}</span>
          <div className="admin-bar-track">
            <div className="admin-bar-fill" style={{ width: `${Math.min(100, it.share_pct || 0)}%` }} />
          </div>
          <span>
            {NUM.format(it.events || 0)} eventos · {NUM.format(it.credits || 0)} créditos
          </span>
        </div>
      ))}
    </div>
  );
}

function StatusBadge({ status }) {
  const cls =
    status === "paid" ? "admin-badge-ok" : status === "pending" ? "admin-badge-pending" : "admin-badge-off";
  return <span className={`admin-badge ${cls}`}>{status}</span>;
}

function OverviewTab() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    authFetch("/admin/overview")
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message || "No se pudo cargar el resumen"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <p>Cargando resumen…</p>;
  if (error) return <p className="staging-error">{error}</p>;
  if (!data) return null;

  const kpis = [
    ["Usuarios registrados", NUM.format(data.users_total)],
    ["Activos últimos 30 días", NUM.format(data.users_active_30d)],
    ["Registros últimos 7 días", NUM.format(data.users_registered_7d)],
    ["Registros últimos 30 días", NUM.format(data.users_registered_30d)],
    ["Créditos vendidos", NUM.format(data.credits_sold)],
    ["Créditos consumidos", NUM.format(data.credits_consumed)],
    ["Créditos pendientes", NUM.format(data.credits_outstanding)],
    ["Ingresos totales", COP.format(data.revenue_cop_total || 0)],
    ["Pagos pagados", NUM.format(data.payments_paid_count)],
    ["Pagos pendientes", NUM.format(data.payments_pending_count)],
  ];

  return (
    <div>
      <div className="admin-kpi-grid">
        {kpis.map(([label, value]) => (
          <div className="admin-kpi" key={label}>
            <p className="admin-kpi-label">{label}</p>
            <p className="admin-kpi-value">{value}</p>
          </div>
        ))}
      </div>
      <div className="card">
        <h3>Uso por proveedor</h3>
        <ShareBars items={data.usage_by_provider} />
      </div>
    </div>
  );
}

function UserDetail({ userId, onClose, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tempPassword, setTempPassword] = useState("");
  const [creditsDelta, setCreditsDelta] = useState("");
  const [creditsReason, setCreditsReason] = useState("");

  function load() {
    setError("");
    authFetch(`/admin/users/${userId}`)
      .then(setDetail)
      .catch((e) => setError(e.message || "No se pudo cargar el usuario"));
  }

  useEffect(load, [userId]);

  async function toggle(field) {
    if (!detail) return;
    setBusy(true);
    setError("");
    try {
      const body = { [field]: !detail[field] };
      const updated = await authFetch(`/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setDetail((prev) => ({ ...prev, ...updated }));
      onChanged?.();
    } catch (e) {
      setError(e.message || "No se pudo actualizar");
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword() {
    if (!window.confirm("¿Restablecer la contraseña de este usuario? Se generará una nueva contraseña temporal.")) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await authFetch(`/admin/users/${userId}/reset-password`, { method: "POST" });
      setTempPassword(res.temporary_password);
    } catch (e) {
      setError(e.message || "No se pudo restablecer la contraseña");
    } finally {
      setBusy(false);
    }
  }

  async function adjustCredits(e) {
    e.preventDefault();
    const delta = Number(creditsDelta);
    if (!delta) return;
    if (!window.confirm(`¿Aplicar ${delta > 0 ? "+" : ""}${delta} créditos a este usuario?`)) return;
    setBusy(true);
    setError("");
    try {
      const res = await authFetch(`/admin/users/${userId}/credits`, {
        method: "POST",
        body: JSON.stringify({ delta, reason: creditsReason || "Ajuste manual" }),
      });
      setDetail((prev) => ({ ...prev, credits_balance: res.balance }));
      setCreditsDelta("");
      setCreditsReason("");
      onChanged?.();
    } catch (e) {
      setError(e.message || "No se pudo ajustar el saldo");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-detail-backdrop" onClick={onClose}>
      <div className="admin-detail-card" onClick={(e) => e.stopPropagation()}>
        <div className="admin-detail-head">
          <h3>{detail ? detail.email : "Cargando…"}</h3>
          <button onClick={onClose}>Cerrar</button>
        </div>
        {error && <p className="staging-error">{error}</p>}
        {!detail ? (
          <p>Cargando…</p>
        ) : (
          <>
            <p>
              {detail.full_name || "—"} · tenant <code>{detail.tenant_id}</code>
            </p>
            <p>
              Registro: {fmtDate(detail.created_at)} · Último acceso: {fmtDate(detail.last_login_at)}
            </p>
            <p>
              Estado:{" "}
              <span className={`admin-badge ${detail.is_active ? "admin-badge-ok" : "admin-badge-off"}`}>
                {detail.is_active ? "activo" : "inactivo"}
              </span>{" "}
              {detail.is_admin && <span className="admin-badge admin-badge-pending">admin</span>}
            </p>
            <p>
              Saldo: <strong>{NUM.format(detail.credits_balance)}</strong> créditos · Consumidos:{" "}
              {NUM.format(detail.credits_consumed)} · Runs: {NUM.format(detail.runs_total)}
            </p>
            <p>
              Total pagado: {COP.format(detail.paid_total_cop || 0)} · Último pago: {fmtDate(detail.last_payment_at)}
            </p>
            <p>
              Contraseña: cifrada (irreversible) — <code>{detail.password_algo}</code>
            </p>

            <div className="admin-detail-actions">
              <button disabled={busy} onClick={() => toggle("is_active")}>
                {detail.is_active ? "Desactivar" : "Activar"}
              </button>
              <button disabled={busy} onClick={() => toggle("is_admin")}>
                {detail.is_admin ? "Quitar admin" : "Hacer admin"}
              </button>
              <button disabled={busy} onClick={resetPassword}>
                Restablecer contraseña
              </button>
            </div>
            <p className="admin-empty" style={{ marginTop: 4 }}>
              Nota: tras Auth0 este botón pasará a abrir el dashboard del IdP; hoy genera una clave temporal local.
            </p>

            {tempPassword && (
              <div className="admin-temp-pass">
                <p>
                  Contraseña temporal (se muestra <strong>una sola vez</strong>, guárdala ahora):
                </p>
                <p>
                  <code>{tempPassword}</code>{" "}
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(tempPassword)}
                  >
                    Copiar
                  </button>
                </p>
              </div>
            )}

            <form onSubmit={adjustCredits} className="admin-detail-actions">
              <input
                type="number"
                placeholder="Delta (+/-)"
                value={creditsDelta}
                onChange={(e) => setCreditsDelta(e.target.value)}
                style={{ maxWidth: 140 }}
              />
              <input
                type="text"
                placeholder="Motivo"
                value={creditsReason}
                onChange={(e) => setCreditsReason(e.target.value)}
                style={{ maxWidth: 220 }}
              />
              <button type="submit" disabled={busy || !creditsDelta}>
                Ajustar créditos
              </button>
            </form>

            <h4>Uso por proveedor</h4>
            <ShareBars items={detail.usage_by_provider} />

            <h4>Pagos</h4>
            {detail.payments && detail.payments.length > 0 ? (
              <div className="admin-table-wrap">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Referencia</th>
                      <th>Proveedor</th>
                      <th>Monto</th>
                      <th>Créditos</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.payments.map((p) => (
                      <tr key={p.id}>
                        <td>{fmtDate(p.created_at)}</td>
                        <td>{p.reference}</td>
                        <td>{p.provider}</td>
                        <td>{COP.format(p.amount_cop || 0)}</td>
                        <td>{NUM.format(p.credits_added)}</td>
                        <td><StatusBadge status={p.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="admin-empty">Sin pagos.</p>
            )}

            <h4>Runs recientes</h4>
            {detail.recent_runs && detail.recent_runs.length > 0 ? (
              <div className="admin-table-wrap">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Formato</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.recent_runs.map((r) => (
                      <tr key={r.id}>
                        <td>{fmtDate(r.created_at)}</td>
                        <td>{r.content_format}</td>
                        <td>{r.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="admin-empty">Sin runs.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function UsersTab() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounced(query, 400);
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    setOffset(0);
  }, [debouncedQuery]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (debouncedQuery) params.set("query", debouncedQuery);
    authFetch(`/admin/users?${params.toString()}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message || "No se pudo cargar la lista de usuarios"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [debouncedQuery, offset, reloadTick]);

  return (
    <div>
      <div className="admin-filters">
        <input
          type="text"
          placeholder="Buscar por email o nombre…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ maxWidth: 280 }}
        />
      </div>
      {error && <p className="staging-error">{error}</p>}
      {loading ? (
        <p>Cargando usuarios…</p>
      ) : !data || data.items.length === 0 ? (
        <p className="admin-empty">Sin usuarios para mostrar.</p>
      ) : (
        <>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Nombre</th>
                  <th>Registro</th>
                  <th>Último acceso</th>
                  <th>Estado</th>
                  <th>Saldo</th>
                  <th>Consumidos</th>
                  <th>Runs</th>
                  <th>Pagado</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((u) => (
                  <tr key={u.id} onClick={() => setSelectedId(u.id)}>
                    <td>{u.email}</td>
                    <td>{u.full_name || "—"}</td>
                    <td>{fmtDate(u.created_at)}</td>
                    <td>{fmtDate(u.last_login_at)}</td>
                    <td>
                      <span className={`admin-badge ${u.is_active ? "admin-badge-ok" : "admin-badge-off"}`}>
                        {u.is_active ? "activo" : "inactivo"}
                      </span>
                    </td>
                    <td>{NUM.format(u.credits_balance)}</td>
                    <td>{NUM.format(u.credits_consumed)}</td>
                    <td>{NUM.format(u.runs_total)}</td>
                    <td>{COP.format(u.paid_total_cop || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="admin-pagination">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
              Anterior
            </button>
            <span>
              {offset + 1}–{Math.min(offset + limit, data.total)} de {NUM.format(data.total)}
            </span>
            <button disabled={offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>
              Siguiente
            </button>
          </div>
        </>
      )}
      {selectedId && (
        <UserDetail
          userId={selectedId}
          onClose={() => setSelectedId(null)}
          onChanged={() => setReloadTick((t) => t + 1)}
        />
      )}
    </div>
  );
}

function PaymentsTab() {
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set("status", status);
    authFetch(`/admin/payments?${params.toString()}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message || "No se pudo cargar los pagos"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [status, offset]);

  return (
    <div>
      <div className="admin-filters">
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">Todos</option>
          <option value="paid">Pagados</option>
          <option value="pending">Pendientes</option>
          <option value="failed">Fallidos</option>
        </select>
      </div>
      {error && <p className="staging-error">{error}</p>}
      {loading ? (
        <p>Cargando pagos…</p>
      ) : !data || data.items.length === 0 ? (
        <p className="admin-empty">Sin pagos para mostrar.</p>
      ) : (
        <>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Email</th>
                  <th>Referencia</th>
                  <th>Monto</th>
                  <th>Créditos</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => (
                  <tr key={p.id}>
                    <td>{fmtDate(p.created_at)}</td>
                    <td>{p.email}</td>
                    <td>{p.reference}</td>
                    <td>{COP.format(p.amount_cop || 0)}</td>
                    <td>{NUM.format(p.credits_added)}</td>
                    <td><StatusBadge status={p.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="admin-pagination">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
              Anterior
            </button>
            <span>
              {offset + 1}–{Math.min(offset + limit, data.total)} de {NUM.format(data.total)}
            </span>
            <button disabled={offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>
              Siguiente
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function UsageTab() {
  const [days, setDays] = useState(30);
  const [groupBy, setGroupBy] = useState("provider");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    authFetch(`/admin/usage?group_by=${groupBy}&days=${days}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message || "No se pudo cargar el consumo"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [days, groupBy]);

  return (
    <div>
      <div className="admin-filters">
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Últimos 7 días</option>
          <option value={30}>Últimos 30 días</option>
          <option value={90}>Últimos 90 días</option>
        </select>
        <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
          <option value="provider">Por proveedor</option>
          <option value="user">Por usuario</option>
        </select>
      </div>
      {error && <p className="staging-error">{error}</p>}
      {loading ? (
        <p>Cargando consumo…</p>
      ) : (
        <div className="card">
          <ShareBars items={data?.items?.map((it) => ({ ...it, provider: it.label || it.key }))} />
        </div>
      )}
    </div>
  );
}

const TABS = [
  { id: "overview", label: "Resumen", Component: OverviewTab },
  { id: "users", label: "Usuarios", Component: UsersTab },
  { id: "payments", label: "Pagos", Component: PaymentsTab },
  { id: "usage", label: "Consumo de APIs", Component: UsageTab },
];

export default function AdminPanel() {
  const [tab, setTab] = useState("overview");
  const [forbidden, setForbidden] = useState(false);
  const staging = isStagingMode();

  useEffect(() => {
    if (!staging) return;
    authFetch("/admin/overview").catch((e) => {
      if (e.status === 403) setForbidden(true);
    });
  }, [staging]);

  if (!staging) {
    return (
      <div className="staging-page container">
        <p>Modo staging no activo. Define VITE_STAGING_SAAS=true en el frontend.</p>
        <Link to="/">Volver</Link>
      </div>
    );
  }

  if (forbidden) {
    return (
      <div className="staging-page container">
        <div className="card">
          <h1>No autorizado</h1>
          <p>Tu cuenta no tiene permisos de administrador para ver este panel.</p>
          <Link to="/app" className="staging-btn staging-btn-primary">
            Volver al estudio
          </Link>
        </div>
      </div>
    );
  }

  const Active = TABS.find((t) => t.id === tab)?.Component || OverviewTab;

  return (
    <div className="admin-page">
      <div className="container brand-theme">
        <header className="app-brand-header">
          <BrandMark size={48} to="/app" />
          <div>
            <h1>Panel de administrador</h1>
            <p className="app-brand-sub">Usuarios, créditos, pagos y consumo de APIs</p>
          </div>
          <Link to="/app" className="staging-btn staging-btn-ghost staging-btn-sm" style={{ marginLeft: "auto" }}>
            Volver al estudio
          </Link>
        </header>

        <div className="admin-tabs">
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>

        <Active />
      </div>
    </div>
  );
}
