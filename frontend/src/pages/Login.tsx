import { useId, useRef, useState, type FormEvent } from "react";
import { LoginLayout } from "../layouts/LoginLayout";
import { Alert, Button, Card, FormField, IconButton, Input, LoadingState } from "../ui";
import { loginErrorMessage, type LoginCredentials } from "../services/login";

function PasswordVisibilityIcon({ visible }: { visible: boolean }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />
    {visible && <path d="m3 3 18 18" />}
  </svg>;
}

export function SessionLoading() {
  return <LoginLayout><Card className="atlas-login-card"><LoadingState label="Comprobando sesión…" /></Card></LoginLayout>;
}

export default function Login({ onSignIn }: { onSignIn: (credentials: LoginCredentials) => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const passwordId = useId();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setSubmitting(true);
    setError("");
    try {
      await onSignIn({ email, password });
      setPassword("");
      setPasswordVisible(false);
    } catch (reason) {
      setError(loginErrorMessage(reason));
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  }

  return <LoginLayout>
    <Card className="atlas-login-card">
      <h1 className="atlas-page-title atlas-login-heading">Bienvenido a Atlas</h1>
      <p className="atlas-muted">Inicia sesión para continuar.</p>
      <form className="atlas-login-form" onSubmit={submit} aria-label="Iniciar sesión">
        {error && <div className="atlas-login-feedback"><Alert tone="danger" title="No se pudo iniciar sesión">{error}</Alert></div>}
        <FormField label="Correo electrónico" required>
          <Input name="email" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false}
            value={email} onChange={(event) => setEmail(event.target.value)} readOnly={submitting} />
        </FormField>
        <FormField id={passwordId} label="Contraseña" required>
          <div className="atlas-login-password">
            <Input name="password" type={passwordVisible ? "text" : "password"} autoComplete="current-password" minLength={8} maxLength={128}
              value={password} onChange={(event) => setPassword(event.target.value)} readOnly={submitting} />
            <IconButton label={passwordVisible ? "Ocultar contraseña" : "Mostrar contraseña"} variant="outline" aria-controls={passwordId}
              disabled={submitting} onClick={() => setPasswordVisible((current) => !current)}><PasswordVisibilityIcon visible={passwordVisible} /></IconButton>
          </div>
        </FormField>
        <Button type="submit" size="lg" className="atlas-login-submit" loading={submitting} loadingLabel="Ingresando…">Iniciar sesión</Button>
        <span className="sr-only" role="status">{submitting ? "Validando acceso…" : ""}</span>
      </form>
    </Card>
  </LoginLayout>;
}
