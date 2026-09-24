import { useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { authFetch, isAuth0Configured, isStagingMode } from "./auth";
import BoldCheckout from "./BoldCheckout";
import { BrandMark } from "./BrandMark";
import { Link } from "./RouterLink";

/**
 * Barra superior SaaS: email Auth0, créditos, link Admin, logout Auth0.
 * Sustituye la sesión local (sessionStorage) por useAuth0 + /auth/me.
 */
export default function StagingBar() {
  const { isAuthenticated, user, logout, isLoading } = useAuth0();
  const [credits, setCredits] = useState(null);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    if (!isStagingMode() || !isAuthenticated) return;
    authFetch("/billing/credits")
      .then((d) => setCredits(d.balance))
      .catch(() => setCredits(null));
    authFetch("/auth/me")
      .then((me) => setIsAdmin(Boolean(me.is_admin)))
      .catch(() => setIsAdmin(false));
  }, [isAuthenticated]);

  if (!isStagingMode() || !isAuth0Configured()) return null;
  if (isLoading) return null;

  return (
    <div className="staging-bar brand-theme">
      <div className="staging-bar-inner">
        <BrandMark size={32} className="staging-bar-brand-mark" />
        {isAuthenticated ? (
          <>
            <span className="staging-bar-user">{user?.email || user?.name}</span>
            <span className="staging-bar-credits">
              Créditos: <strong>{credits ?? "…"}</strong>
            </span>
            {isAdmin && (
              <Link to="/admin" className="staging-btn staging-btn-primary staging-btn-sm">
                Admin
              </Link>
            )}
            <details className="staging-bar-pay">
              <summary>Recargar con Bold</summary>
              <BoldCheckout />
            </details>
            <button
              type="button"
              className="staging-btn staging-btn-ghost staging-btn-sm"
              onClick={() =>
                logout({ logoutParams: { returnTo: window.location.origin } })
              }
            >
              Salir
            </button>
          </>
        ) : (
          <Link to="/login" className="staging-btn staging-btn-primary staging-btn-sm">
            Iniciar sesión
          </Link>
        )}
      </div>
    </div>
  );
}
