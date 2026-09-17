import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import AdminPanel from "./AdminPanel";
import { PrivacidadPage, TerminosPage } from "./LegalPages";
import LandingPage from "./LandingPage";
import LoginPage from "./LoginPage";
import StagingBar from "./StagingBar";
import { RouterProvider } from "./RouterLink";
import { isStagingMode, getAuthToken } from "./auth";
import "./styles.css";

function normalizePath(pathname) {
  const p = (pathname || "/").replace(/\/+$/, "") || "/";
  return p;
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
    if (path === "/app" || path.startsWith("/app/")) return App;
    if (path === "/admin" || path.startsWith("/admin/")) return AdminPanel;
  }
  return App;
}

function isProtectedPath(path) {
  return path === "/app" || path.startsWith("/app/") || path === "/admin" || path.startsWith("/admin/");
}

function Root() {
  const [path, setPath] = useState(() => normalizePath(window.location.pathname));

  useEffect(() => {
    const onPop = () => setPath(normalizePath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = (to) => {
    const next = normalizePath(to);
    if (next !== path) {
      window.history.pushState({}, "", next);
      setPath(next);
    }
  };

  const needsLogin = isStagingMode() && isProtectedPath(path) && !getAuthToken();
  const effectivePath = needsLogin ? "/login" : path;

  useEffect(() => {
    if (needsLogin) {
      window.history.replaceState({}, "", "/login");
    }
  }, [needsLogin]);

  const Page = resolvePage(effectivePath);
  const showStagingChrome = isStagingMode() && Page === App;

  return (
    <RouterProvider path={effectivePath} navigate={navigate}>
      {showStagingChrome && <StagingBar />}
      <Page />
    </RouterProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
