import { useEffect, useRef, useState } from "react";
import { authFetch, getAuthToken } from "./auth";

const BOLD_SDK = "https://checkout.bold.co/library/boldPaymentButton.js";

export default function BoldCheckout() {
  const mountRef = useRef(null);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("Cargando botón de pago…");
  const [pack, setPack] = useState(null);

  useEffect(() => {
    if (!getAuthToken()) {
      setHint("Inicia sesión para ver el botón Bold.");
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const cfg = await authFetch("/billing/bold-checkout");
        if (cancelled) return;
        setPack(cfg);
        setHint(
          `Paquete: ${cfg.credits_per_pack} créditos por $${cfg.amount_cop.toLocaleString("es-CO")} COP`
        );
        mountBold(mountRef.current, cfg);
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "No se pudo cargar Bold");
          setHint("");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="staging-bold">
      {hint && !error && <p className="staging-muted">{hint}</p>}
      {error && <p className="staging-error">{error}</p>}
      <div ref={mountRef} id="mdia-bold-mount" />
      {pack && (
        <p className="staging-muted staging-small">
          Tras pagar, los créditos se acreditan automáticamente vía webhook Bold.
        </p>
      )}
    </div>
  );
}

function mountBold(mount, cfg) {
  if (!mount) return;
  mount.innerHTML = "";
  const btn = document.createElement("script");
  btn.src = BOLD_SDK;
  btn.setAttribute("data-bold-button", "");
  btn.setAttribute("data-order-id", cfg.order_id);
  btn.setAttribute("data-currency", cfg.currency);
  btn.setAttribute("data-amount", String(cfg.amount_cop));
  btn.setAttribute("data-api-key", cfg.api_key);
  btn.setAttribute("data-integrity-signature", cfg.integrity_signature);
  btn.setAttribute("data-description", cfg.description);
  btn.setAttribute("data-redirection-url", cfg.redirection_url);
  btn.setAttribute("data-render-mode", "embedded");
  mount.appendChild(btn);
}
