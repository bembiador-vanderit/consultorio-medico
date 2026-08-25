import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { User } from "../types/user";

export default function Dashboard({ user, patientsVersion }: { user: User; patientsVersion: number }) {
  const [patientCount, setPatientCount] = useState<number | null>(null);
  const [loadingPatients, setLoadingPatients] = useState(true);

  async function loadPatientCount() {
    try {
      setLoadingPatients(true);
      const { data } = await api.get<{ count: number }>("/patients/count");
      setPatientCount(data.count);
    } catch (error) {
      console.error("Error cargando cantidad de pacientes:", error);
      setPatientCount(null);
    } finally {
      setLoadingPatients(false);
    }
  }

  useEffect(() => {
    loadPatientCount();
  }, [patientsVersion]);

  return (
    <section>
      <p className="text-sm font-medium text-teal-700">Dashboard</p>
      <h2 className="mt-1 text-3xl font-bold">Bienvenido, {user.full_name}</h2>
      <p className="mt-2 text-slate-500">Resumen general del consultorio.</p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard title="Pacientes" value={loadingPatients ? "..." : patientCount ?? "—"} />
        <StatCard title="Citas de hoy" value="0" />
        <StatCard title="Usuarios" value={user.roles.includes("admin") ? "1" : "—"} />
      </div>

      <div className="mt-6 rounded-xl border bg-white p-6 shadow-sm">
        <h3 className="font-bold">Acciones rápidas</h3>
        <p className="mt-1 text-sm text-slate-500">
          Utilice el menú para acceder a los módulos del sistema.
        </p>
      </div>
    </section>
  );
}

function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded-xl border bg-white p-6 shadow-sm">
      <p className="text-sm text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-bold">{value}</p>
    </div>
  );
}
