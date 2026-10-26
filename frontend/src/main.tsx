import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";
import QueueDisplayPage from "./pages/QueueDisplayPage";

// Compile-time DEV gate: the catalogue and role simulator are absent in production.
const FoundationPreview = import.meta.env.DEV
  ? lazy(() => import("./dev/FoundationPreview"))
  : null;
const showFoundation = FoundationPreview && window.location.pathname === "/__dev/ui-v2";
const displayToken = window.location.pathname.match(/^\/queue-display\/([A-Za-z0-9_-]+)\/?$/)?.[1];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {displayToken ? (import.meta.env.VITE_QUEUE_DISPLAYS_ENABLED === "true"
      ? <QueueDisplayPage token={displayToken} />
      : <main role="status">Pantalla no disponible</main>)
      : showFoundation ? <Suspense fallback={<p role="status">Cargando catálogo…</p>}><FoundationPreview /></Suspense> : <App />}
  </StrictMode>,
);
