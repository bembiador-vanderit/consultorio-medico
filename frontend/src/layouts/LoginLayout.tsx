import type { ReactNode } from "react";
import "./login.css";

/** Unauthenticated layout only. The A mark is replaceable, not a final logo. */
export function LoginLayout({ children }: { children: ReactNode }) {
  return <main className="atlas-root atlas-login">
    <div className="atlas-login-content">
      <aside className="atlas-login-clinical" aria-label="Atlas Consultorio">
        <p className="atlas-login-statement">Cuidar también<br /> es innovar</p>
        <div className="atlas-login-art" aria-hidden="true"><span className="atlas-login-orbit" /><span className="atlas-login-cross" /></div>
        <header className="atlas-login-identity">
          <div className="atlas-login-brand">
            <span className="atlas-login-mark" aria-hidden="true">A</span>
            <p className="atlas-section-title">Atlas Consultorio</p>
          </div>
          <p className="atlas-login-brand-copy">Gestión médica simple,<br />segura y confiable.</p>
        </header>
      </aside>
      <div className="atlas-login-access">
        {children}
        <p className="atlas-login-note atlas-help">Acceso exclusivo para personal autorizado.</p>
      </div>
    </div>
  </main>;
}
