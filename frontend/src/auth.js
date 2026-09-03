const TOKEN_KEY = "access_token";
const USER_KEY = "staging_user";

export function isStagingMode() {
  return import.meta.env.VITE_STAGING_SAAS === "true";
}

export function getAuthToken() {
  if (typeof sessionStorage === "undefined") return "";
  return (
    sessionStorage.getItem(TOKEN_KEY) ||
    sessionStorage.getItem("api_key") ||
    import.meta.env.VITE_API_KEY ||
    ""
  );
}

export function saveAuthSession({ access_token, email, tenant_id, full_name, credits_balance }) {
  sessionStorage.setItem(TOKEN_KEY, access_token);
  sessionStorage.setItem(
    USER_KEY,
    JSON.stringify({ email, tenant_id, full_name, credits_balance })
  );
}

export function loadAuthUser() {
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function clearAuthSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
  sessionStorage.removeItem("api_key");
}

export function apiBase() {
  const explicit = import.meta.env.VITE_API_URL;
  if (explicit === "" || explicit === "/") return "";
  if (explicit) return String(explicit).replace(/\/$/, "");
  if (import.meta.env.DEV) return "";
  return "";
}

export async function authFetch(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getAuthToken();
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
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}
