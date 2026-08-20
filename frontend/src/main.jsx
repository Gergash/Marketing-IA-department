import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { PrivacidadPage, TerminosPage } from "./LegalPages";
import "./styles.css";

const path = window.location.pathname.replace(/\/+$/, "") || "/";
const Page =
  path === "/terminos" || path === "/terms" || path === "/terms-of-service"
    ? TerminosPage
    : path === "/privacidad" || path === "/privacy" || path === "/privacy-policy"
      ? PrivacidadPage
      : App;

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Page />
  </React.StrictMode>
);
