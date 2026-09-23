import React, { useCallback, useEffect, useLayoutEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import App from "./App";
import AdminPanel from "./AdminPanel";
import { PrivacidadPage, TerminosPage } from "./LegalPages";
import LandingPage from "./LandingPage";
import LoginPage from "./LoginPage";
import StagingBar from "./StagingBar";
import { RouterProvider } from "./RouterLink";
import {
  getAuth0ClientId,
  getAuth0Domain,
  getAuthToken,
  isAuth0Configured,
  isJwtUnexpired,
  isStagingMode,
  setAuth0TokenGetter,
} from "./auth";
import "./styles.css";

/**
 * Router SPA + Auth0.
 *
 * Cambios SaaS:
 * - Identidad solo Auth0 (sin sessionStorage JWT).
 * - Rutas /app y /admin protegidas; paths desconocidos (p.ej. /ladmin) → landing
 *   (antes caían en App y bypaseaban login).
 * - Esperamos ID token antes de montar el estudio para no disparar 401→/login en bucle.
 */

function normalizePath(pathname) {
  const p = (pathname || "/").replace(/\/+$/, "") || "/";
  return p;
}

function isLegalPath(path) {
  return (
    path === "/terminos" ||
    path === "/terms" ||
    path === "/terms-of-service" ||
    path === "/privacidad" ||
    path === "/privacy" ||
    path === "/privacy-policy"
  );
}

function isStudioPath(path) {
  return path === "/app" || path.startsWith("/app/");
}

function isAdminPath(path) {
  return path === "/admin" || path.startsWith("/admin/");
}

function resolvePage(path) {
  if (path === "/terminos" || path === "/terms" || path === "/terms-of-service") {
    return TerminosPage;
  }
  if (path === "/privacidad" || path === "/privacy" || path === "/privacy-policy") {
    return PrivacidadPage;
  }
  if (isStagingMode()) {
    if (path === "/" || path === "/landing") return LandingPage;
    if (path === "/login" || path === "/registro") return LoginPage;
    if (isStudioPath(path)) return App;
    if (isAdminPath(path)) return AdminPanel;
    // Unknown paths (e.g. /ladmin) must NOT fall through to App — that bypassed Auth0.
    return LandingPage;
  }
  return App;
}

function isProtectedPath(path) {
  return isStudioPath(path) || isAdminPath(path);
}

function isUnknownStagingPath(path) {
  if (!isStagingMode()) return false;
  if (isLegalPath(path)) return false;
  if (path === "/" || path === "/landing") return false;
  if (path === "/login" || path === "/registro") return false;
  if (isProtectedPath(path)) return false;
  return true;
}

function Root({ auth0Authenticated = false, auth0Loading = false }) {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname));
  // tokenReady: evita montar App antes de que exista Bearer Auth0.
  const [tokenReady, setTokenReady] = useState(false);
  const hasSession = auth0Authenticated;
  const authReady = !auth0Loading;

  useEffect(() => {
    const onPop = () => setPath(normalizePath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((to) => {
    const next = normalizePath(to);
    setPath((current) => {
      if (next === current) return current;
      window.history.pushState({}, "", next);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!auth0Authenticated) {
      setTokenReady(false);
      return undefined;
    }
    let alive = true;
    getAuthToken().then((token) => {
      if (alive) setTokenReady(Boolean(token));
    });
    // Fail-open: si Auth0 refresh tarda, no congelar UI (API acepta leeway de reloj).
    const failOpen = setTimeout(() => {
      if (alive) setTokenReady(true);
    }, 4000);
    return () => {
      alive = false;
      clearTimeout(failOpen);
    };
  }, [auth0Authenticated]);

  const unknownStaging = isUnknownStagingPath(path);
  const needsLogin = isStagingMode() && isProtectedPath(path) && authReady && !hasSession;
  const waitingToken = isStagingMode() && hasSession && isProtectedPath(path) && !tokenReady;
  const effectivePath = needsLogin ? "/login" : unknownStaging ? "/" : path;

  useEffect(() => {
    if (needsLogin) {
      window.history.replaceState({}, "", "/login");
      setPath("/login");
      return;
    }
    if (unknownStaging) {
      window.history.replaceState({}, "", "/");
      setPath("/");
    }
  }, [needsLogin, unknownStaging]);

  // Ya autenticado + token: aterrizar en /app desde landing/login.
  useEffect(() => {
    if (!auth0Authenticated || !tokenReady) return;
    const p = normalizePath(window.location.pathname);
    if (p === "/" || p === "/login" || p === "/registro" || isUnknownStagingPath(p)) {
      window.history.replaceState({}, "", "/app");
      setPath("/app");
    }
  }, [auth0Authenticated, tokenReady]);

  if (auth0Loading || waitingToken) {
    return (
      <div className="staging-page container brand-theme">
        <p>Cargando sesión Auth0…</p>
      </div>
    );
  }

  if (isStagingMode() && !isAuth0Configured()) {
    return (
      <div className="staging-page container brand-theme">
        <p>
          Auth0 no está configurado. Define <code>VITE_AUTH0_DOMAIN</code> y{" "}
          <code>VITE_AUTH0_CLIENT_ID</code> en <code>frontend/.env.local</code>.
        </p>
      </div>
    );
  }

  const Page = resolvePage(effectivePath);
  const showStagingChrome = isStagingMode() && Page === App;

  return (
    <RouterProvider path={effectivePath} navigate={navigate}>
      {showStagingChrome && <StagingBar />}
      <Page />
    </RouterProvider>
  );
}

/** Cablea getIdTokenClaims → auth.js; refresca con getAccessTokenSilently si el ID expiró. */
function Auth0Root() {
  const { isAuthenticated, isLoading, getIdTokenClaims, getAccessTokenSilently } = useAuth0();

  useLayoutEffect(() => {
    setAuth0TokenGetter(async () => {
      const readId = async () => {
        const claims = await getIdTokenClaims();
        return claims?.__raw || "";
      };
      let raw = await readId();
      if (raw && isJwtUnexpired(raw)) return raw;
      try {
        // cacheMode off fuerza refresh; sin Resource Server a veces no hay access token.
        await getAccessTokenSilently({ cacheMode: "off", timeoutInSeconds: 20 });
      } catch {
        /* reintentamos ID token de todos modos */
      }
      raw = await readId();
      return raw || "";
    });
  }, [getIdTokenClaims, getAccessTokenSilently]);

  return <Root auth0Authenticated={isAuthenticated} auth0Loading={isLoading} />;
}

function onAuth0Redirect(appState) {
  const to = appState?.returnTo || "/app";
  window.history.replaceState({}, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

const root = ReactDOM.createRoot(document.getElementById("root"));

if (isAuth0Configured()) {
  root.render(
    <React.StrictMode>
      <Auth0Provider
        domain={getAuth0Domain()}
        clientId={getAuth0ClientId()}
        authorizationParams={{
          redirect_uri: window.location.origin,
          scope: "openid profile email",
        }}
        onRedirectCallback={onAuth0Redirect}
        cacheLocation="localstorage"
        useRefreshTokens
        useRefreshTokensFallback
      >
        <Auth0Root />
      </Auth0Provider>
    </React.StrictMode>
  );
} else {
  // Sin Auth0: studio clásico (API key / tenant demo).
  root.render(
    <React.StrictMode>
      <Root />
    </React.StrictMode>
  );
}
