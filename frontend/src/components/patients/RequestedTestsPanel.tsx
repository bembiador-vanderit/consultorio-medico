import { useState } from "react";

type Props = {
  patientName: string;
  consultationDate: string;
  value: string;
  onChange: (value: string) => void;
};

export default function RequestedTestsPanel({ patientName, consultationDate, value, onChange }: Props) {
  const [open, setOpen] = useState(false);

  function printOrder() {
    const popup = window.open("", "_blank", "width=800,height=900");
    if (!popup) return;
    const items = value.split("\n").map((item) => item.trim()).filter(Boolean);
    popup.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Orden de análisis y pruebas</title><style>body{font-family:Arial,sans-serif;margin:48px;color:#111}h1{font-size:22px;margin-bottom:6px}.muted{color:#555;font-size:13px}.line{border-bottom:1px solid #ddd;padding:10px 0}footer{margin-top:60px;text-align:center;color:#666;font-size:12px}@media print{button{display:none}}</style></head><body><h1>Orden de análisis y pruebas</h1><p class="muted"><strong>Paciente:</strong> ${patientName}</p><p class="muted"><strong>Fecha de consulta:</strong> ${consultationDate}</p><hr>${items.length ? items.map((item) => `<div class="line">☐ ${item.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</div>`).join("") : "<p>No se indicaron análisis o pruebas.</p>"}<footer>Documento emitido por el médico tratante.</footer><script>window.onload=()=>window.print()</script></body></html>`);
    popup.document.close();
  }

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="font-semibold text-indigo-900">Análisis y pruebas indicadas</h4>
          <p className="text-xs text-indigo-700">Opcional: se guarda junto con esta consulta.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setOpen((current) => !current)} className="rounded-lg border border-indigo-300 bg-white px-3 py-2 text-sm font-medium text-indigo-800">{open ? "Ocultar" : "Agregar análisis / pruebas"}</button>
          <button type="button" onClick={printOrder} disabled={!value.trim()} className="rounded-lg bg-indigo-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-40">🖨️ Imprimir orden</button>
        </div>
      </div>
      {open && <div className="mt-4"><label className="block text-sm font-medium text-slate-700">Un análisis o prueba por línea<textarea value={value} onChange={(event) => onChange(event.target.value)} rows={7} placeholder={'Hemograma\nGlucosa en sangre\nPerfil lipídico\nRadiografía de tórax'} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label></div>}
    </div>
  );
}
