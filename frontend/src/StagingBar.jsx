import { useEffect, useState } from "react";
import { authFetch, clearAuthSession, getAuthToken, isStagingMode, loadAuthUser } from "./auth";
import BoldCheckout from "./BoldCheckout";
import { Link, useNavigate } from "./RouterLink";

export default function StagingBar() {
  const navigate = useNavigate();
  const [credits, setCredits] = useState(null);
  const user = loadAuthUser();

  useEffect(() => {
    if (!isStagingMode() || !getAuthToken()) return;
    authFetch("/billing/credits")
      .then((d) => setCredits(d.balance))
      .catch(() => setCredits(null));
  }, []);

  if (!isStagingMode()) return null;

  return (
    <div className="staging-bar">
      <div className="staging-bar-inner">
        <Link to="/" className="staging-bar-brand">
          Marketing Agéntico
        </Link>
        {user ? (
          <>
            <span className="staging-bar-user">{user.email}</span>
            <span className="staging-bar-credits">
              Créditos: <strong>{credits ?? user.credits_balance ?? "…"}</strong>
            </span>
            <details className="staging-bar-pay">
              <summary>Recargar con Bold</summary>
              <BoldCheckout />
            </details>
            <button
              type="button"
              className="staging-btn staging-btn-ghost staging-btn-sm"
              onClick={() => {
                clearAuthSession();
                navigate("/login");
              }}
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
