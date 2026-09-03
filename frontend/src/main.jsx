import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { PrivacidadPage, TerminosPage } from "./LegalPages";
import LandingPage from "./LandingPage";
import LoginPage from "./LoginPage";
import StagingBar from "./StagingBar";
import { RouterProvider } from "./RouterLink";
import { isStagingMode } from "./auth";
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
  }
  return App;
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

  const Page = resolvePage(path);
  const showStagingChrome = isStagingMode() && Page === App;

  return (
    <RouterProvider path={path} navigate={navigate}>
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
