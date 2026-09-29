import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";
import { Button, Card, LoadingState } from "../ui";
import "./platform.css";

type Organization = { id: number; name: string; slug: string; is_active: boolean };

export default function Platform({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let current = true;
    api.get<Organization[]>("/platform/organizations")
      .then(({ data }) => { if (current) setOrganizations(data); })
      .catch(() => { if (current) setError(true); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, []);
  return <main className="platform-page">
    <header className="platform-header atlas-card"><div><p className="atlas-caption">Administración global</p><h1>Plataforma Atlas</h1><p className="atlas-muted">{user.full_name}</p></div><Button variant="outline" onClick={onSignOut}>Cerrar sesión</Button></header>
    <Card className="platform-organizations" aria-label="Organizaciones">
      <div><p className="atlas-caption">Contexto de plataforma</p><h2>Organizaciones</h2><p className="atlas-muted">Inventario administrativo. Los datos operativos se consultan únicamente dentro de cada tenant autorizado.</p></div>
      {loading ? <LoadingState label="Cargando organizaciones…" /> : error ? <p role="alert">No se pudo cargar la lista.</p> :
        <ul>{organizations.map((organization) => <li key={organization.id}>
          <strong>{organization.name}</strong><span>{organization.is_active ? "Activa" : "Inactiva"}</span>
        </li>)}</ul>}
    </Card>
  </main>;
}
