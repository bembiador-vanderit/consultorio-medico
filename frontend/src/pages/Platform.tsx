import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";

type Organization = { id: number; name: string; slug: string; is_active: boolean };

export default function Platform({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [error, setError] = useState(false);
  useEffect(() => {
    let current = true;
    api.get<Organization[]>("/platform/organizations")
      .then(({ data }) => { if (current) setOrganizations(data); })
      .catch(() => { if (current) setError(true); });
    return () => { current = false; };
  }, []);
  return <main className="atlas-operational-workspace">
    <header><h1>Plataforma Atlas</h1><p>{user.full_name}</p><button type="button" onClick={onSignOut}>Cerrar sesión</button></header>
    <section aria-label="Organizaciones">
      <h2>Organizaciones</h2>
      {error ? <p>No se pudo cargar la lista.</p> :
        <ul>{organizations.map((organization) => <li key={organization.id}>
          {organization.name} · {organization.is_active ? "Activa" : "Inactiva"}
        </li>)}</ul>}
    </section>
  </main>;
}
