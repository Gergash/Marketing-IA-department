import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate } from "./RouterLink";
import { isAuth0Configured, isStagingMode } from "./auth";
import { BrandMark } from "./BrandMark";
import { Link } from "./RouterLink";
import "./staging.css";

/**
 * Login SaaS: solo Auth0 Universal Login.
 * Sustituye el formulario email/password local (endpoints /auth/login|register → 410).
 * "Crear cuenta" usa screen_hint=signup en el mismo tenant Auth0.
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const auth0On = isAuth0Configured();
  const { loginWithRedirect, isAuthenticated, isLoading, user, error } = useAuth0();

  if (!isStagingMode()) {
    return (
      <div className="staging-page container">
        <p>Modo staging no activo. Define VITE_STAGING_SAAS=true en el frontend.</p>
        <Link to="/">Volver</Link>
      </div>
    );
  }

  if (!auth0On) {
    return (
      <div className="staging-page container">
        <p>Auth0 no configurado (VITE_AUTH0_DOMAIN / VITE_AUTH0_CLIENT_ID).</p>
        <Link to="/">Volver</Link>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="staging-page brand-theme">
        <div className="container staging-auth-wrap">
          <BrandMark size={48} />
          <p>Cargando Auth0…</p>
        </div>
      </div>
    );
  }

  if (isAuthenticated) {
    return (
      <div className="staging-page brand-theme">
        <div className="container staging-auth-wrap">
          <BrandMark size={48} />
          <div className="card staging-auth-card">
            <h1>Sesión Auth0</h1>
            <p>
              Conectado como <strong>{user?.email || user?.name}</strong>
            </p>
            <div className="staging-cta-row">
              <button
                type="button"
                className="staging-btn staging-btn-primary"
                onClick={() => navigate("/app")}
              >
                Ir al estudio
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="staging-page brand-theme">
      <div className="container staging-auth-wrap">
        <BrandMark size={48} />
        <div className="card staging-auth-card">
          <h1>Iniciar sesión</h1>
          <p className="staging-muted">
            Accede con Auth0 Universal Login (única identidad de la plataforma).
          </p>
          {error && <p className="staging-error">{error.message}</p>}
          <div className="staging-cta-row" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <button
              type="button"
              className="staging-btn staging-btn-primary"
              onClick={() => loginWithRedirect({ appState: { returnTo: "/app" } })}
            >
              Continuar con Auth0
            </button>
            <button
              type="button"
              className="staging-btn staging-btn-ghost"
              onClick={() =>
                loginWithRedirect({
                  appState: { returnTo: "/app" },
                  authorizationParams: { screen_hint: "signup" },
                })
              }
            >
              Crear cuenta
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
