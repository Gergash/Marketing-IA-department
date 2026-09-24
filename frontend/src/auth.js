/**
 * Auth0-only session helpers for the Marketing DEPA SPA.
 *
 * Cambio vs login local: ya no hay JWT en sessionStorage ni email/password.
 * El ID token lo entrega Auth0Provider vía `setAuth0TokenGetter` (ver main.jsx).
 * El backend valida RS256/JWKS y hace upsert de AppUser + wallet.
 */

/** Getter async registrado por Auth0Root; null hasta que Auth0 monte. */
let _auth0TokenGetter = null;

/** Flag bake-time Vite: sin esto no hay landing/login SaaS. */
export function isStagingMode() {
  return import.meta.env.VITE_STAGING_SAAS === "true";
}

export function isAuth0Configured() {
  return Boolean(
    import.meta.env.VITE_AUTH0_DOMAIN && import.meta.env.VITE_AUTH0_CLIENT_ID
  );
}

export function getAuth0Domain() {
  return import.meta.env.VITE_AUTH0_DOMAIN || "";
}

export function getAuth0ClientId() {
  return import.meta.env.VITE_AUTH0_CLIENT_ID || "";
}

/** Register async getter that returns the Auth0 ID token (raw JWT). */
export function setAuth0TokenGetter(fn) {
  _auth0TokenGetter = typeof fn === "function" ? fn : null;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * True si el JWT aún no venció.
 * skewSec positivo = exigir N segundos de vida restante.
 * skewSec negativo = aceptar tokens caducados hasta |N| s (reloj local vs Auth0).
 * Default -600: evita bucles 401 por drift de reloj en Windows.
 */
export function isJwtUnexpired(raw, skewSec = -600) {
  try {
    const part = (raw || "").split(".")[1];
    if (!part) return false;
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(json);
    return typeof payload.exp === "number" && payload.exp > Date.now() / 1000 + skewSec;
  } catch {
    return false;
  }
}

/**
 * ID token Auth0 para Authorization: Bearer.
 * Reintenta el getter (Auth0 a veces tarda al montar).
 * Si el refresh falla, igual entrega el último JWT: el API tiene leeway de exp.
 */
export async function getAuthToken({ retries = 12, delayMs = 100 } = {}) {
  let last = "";
  for (let i = 0; i <= retries; i += 1) {
    if (_auth0TokenGetter) {
      try {
        const t = await _auth0TokenGetter();
        if (t) {
          last = t;
          if (isJwtUnexpired(t)) return t;
        }
      } catch {
        /* retry */
      }
    }
    if (i < retries) await sleep(delayMs);
  }
  return last;
}

export function apiBase() {
  const explicit = import.meta.env.VITE_API_URL;
  if (explicit === "" || explicit === "/") return "";
  if (explicit) return String(explicit).replace(/\/$/, "");
  if (import.meta.env.DEV) return "";
  return "";
}

/**
 * fetch autenticado al gateway `/api…`.
 * No fuerza Content-Type en FormData (brand manual / uploads).
 * En staging, 401 se propaga como Error (el guard de ruta en main.jsx decide login).
 */
export async function authFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const token = await getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${apiBase()}/api${path}`, { ...options, headers });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail = data.detail || text || res.statusText;
    if (res.status === 401 && isStagingMode()) {
      throw new Error(
        typeof detail === "string" ? detail : "No autorizado. Recarga e inicia sesión con Auth0."
      );
    }
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return data;
}
