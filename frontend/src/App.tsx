const modules = [
  "Pacientes",
  "Agenda",
  "Consultas",
  "Estudios",
  "Recetas",
  "Reportes",
];

function App() {
  return (
    <main className="min-h-screen bg-slate-50 p-6 text-slate-900">
      <section className="mx-auto max-w-5xl">
        <p className="text-sm font-semibold uppercase tracking-widest text-teal-700">
          Consultorio Médico
        </p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight">
          Base del sistema lista para crecer
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-slate-600">
          La Fase 0 establece la infraestructura. Los módulos clínicos se
          implementarán de forma gradual, con seguridad y privacidad como prioridad.
        </p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((module) => (
            <article key={module} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="font-semibold">{module}</h2>
              <p className="mt-2 text-sm text-slate-600">
                Próximamente
              </p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

export default App;
