import { useState } from "react";
import { Link, useNavigate } from "./RouterLink";
import { authFetch, isStagingMode, saveAuthSession } from "./auth";
import BoldCheckout from "./BoldCheckout";
import "./staging.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!isStagingMode()) {
    return (
      <div className="staging-page container">
        <p>Modo staging no activo. Define VITE_STAGING_SAAS=true en el frontend.</p>
        <Link to="/">Volver</Link>
      </div>
    );
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const path = mode === "register" ? "/auth/register" : "/auth/login";
      const body =
        mode === "register"
          ? { email, password, full_name: fullName }
          : { email, password };
      const data = await authFetch(path, { method: "POST", body: JSON.stringify(body) });
      saveAuthSession(data);
      setSession(data);
    } catch (err) {
      setError(err.message || "Error de autenticación");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="staging-page">
      <div className="container staging-auth-wrap">
        <Link to="/" className="staging-back">
          ← Marketing Agéntico
        </Link>

        {!session ? (
          <div className="card staging-auth-card">
            <h1>{mode === "register" ? "Crear cuenta" : "Iniciar sesión"}</h1>
            <p className="staging-muted">
              Un correo por cuenta. Tras registrarte verás el botón de pago Bold para recargar créditos.
            </p>

            <div className="staging-tabs">
              <button
                type="button"
                className={mode === "register" ? "active" : ""}
                onClick={() => setMode("register")}
              >
                Registro
              </button>
              <button
                type="button"
                className={mode === "login" ? "active" : ""}
                onClick={() => setMode("login")}
              >
                Login
              </button>
            </div>

            <form onSubmit={submit}>
              {mode === "register" && (
                <label>
                  Nombre
                  <input
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Tu nombre o empresa"
                  />
                </label>
              )}
              <label>
                Correo
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="tu@empresa.com"
                />
              </label>
              <label>
                Contraseña
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Mínimo 8 caracteres"
                />
              </label>
              {error && <p className="staging-error">{error}</p>}
              <button type="submit" className="staging-btn staging-btn-primary" disabled={loading}>
                {loading ? "Procesando…" : mode === "register" ? "Crear cuenta" : "Entrar"}
              </button>
            </form>
          </div>
        ) : (
          <div className="card staging-auth-card">
            <h1>¡Bienvenido, {session.full_name || session.email}!</h1>
            <p>
              Tu cuenta está lista. Créditos actuales: <strong>{session.credits_balance}</strong>
            </p>
            <BoldCheckout />
            <div className="staging-cta-row">
              <button
                type="button"
                className="staging-btn staging-btn-primary"
                onClick={() => navigate("/app")}
              >
                Ir al estudio de marketing
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
