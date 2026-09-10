import type { ReactNode } from "react";
import "./login.css";

/** Unauthenticated layout only. The A mark is replaceable, not a final logo. */
export function LoginLayout({ children }: { children: ReactNode }) {
  return <main className="atlas-root atlas-login">
    <div className="atlas-login-content">
      <header className="atlas-login-brand">
        <span className="atlas-login-mark" aria-hidden="true">A</span>
        <div><p className="atlas-section-title">Atlas Consultorio</p><p className="atlas-help">Gestión del consultorio</p></div>
      </header>
      {children}
      <p className="atlas-login-note atlas-help">Acceso exclusivo para personal autorizado.</p>
    </div>
  </main>;
}
