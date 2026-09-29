import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

// Compile-time DEV gate: the catalogue and role simulator are absent in production.
const FoundationPreview = import.meta.env.DEV
  ? lazy(() => import("./dev/FoundationPreview"))
  : null;
const showFoundation = FoundationPreview && window.location.pathname === "/__dev/ui-v2";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {showFoundation ? <Suspense fallback={<p role="status">Cargando catálogo…</p>}><FoundationPreview /></Suspense> : <App />}
  </StrictMode>,
);
