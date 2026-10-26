import { FormEvent, useEffect, useRef, useState } from "react";
import { Modal } from "../ui/overlays";
import { api } from "../services/api";

type Challenge = { method: string; path: string; resolve: (proof: string) => void; reject: (error: Error) => void };

/** A one-operation challenge. Password and proof stay only in memory. */
export default function ReauthenticationDialog() {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const active = useRef<Challenge | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const interceptor = api.interceptors.response.use(response => response, async error => {
      const config = error.config;
      if (error.response?.status === 401) window.dispatchEvent(new Event("atlas-session-expired"));
      if (error.response?.status !== 428 || !config || config._reauthenticated) throw error;
      if (active.current) throw new Error("Complete primero la confirmación abierta.");
      const proof = await new Promise<string>((resolve, reject) => {
        const path = new URL(api.getUri(config), window.location.origin).pathname;
        active.current = { method: (config.method || "POST").toUpperCase(), path, resolve, reject };
        setError(""); setPassword(""); setChallenge(active.current);
      });
      return api.request({ ...config, _reauthenticated: true, headers: { ...config.headers, "X-Reauthentication": proof } });
    });
    return () => {
      api.interceptors.response.eject(interceptor);
      active.current?.reject(new Error("Confirmación cancelada"));
      active.current = null;
    };
  }, []);
  function cancel() {
    active.current?.reject(new Error("Operación cancelada"));
    active.current = null; setChallenge(null); setPassword("");
  }
  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (!challenge) return;
    setBusy(true); setError("");
    try {
      const { data } = await api.post("/administration/reauthenticate", { password, method: challenge.method, path: challenge.path });
      setPassword(""); active.current = null; setChallenge(null); challenge.resolve(data.proof);
    } catch (reason: any) {
      setPassword(""); setError(reason.response?.data?.detail || "No se pudo confirmar su identidad.");
    } finally { setBusy(false); }
  }
  if (!challenge) return null;
  return <Modal open onClose={cancel} closeDisabled={busy} title="Confirmar cambio sensible">
    <form onSubmit={confirm}>
      <p className="my-3">Confirme su contraseña para completar el cambio que acaba de solicitar.</p>
      <label>Su contraseña<input autoFocus required type="password" autoComplete="current-password" maxLength={128} value={password} onChange={event => setPassword(event.target.value)} className="my-2 w-full rounded border p-2" /></label>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      <div className="mt-4 flex gap-3"><button type="button" disabled={busy} onClick={cancel} className="rounded border px-4 py-2">Cancelar</button><button disabled={busy} className="rounded bg-teal-700 px-4 py-2 text-white">{busy ? "Verificando…" : "Confirmar"}</button></div>
    </form>
  </Modal>;
}
