import { useState } from "react";

import { api } from "../../services/api";
import type { LaboratoryOrder, StudyOrder } from "../../types/clinicalOrder";

type Props = {
  laboratoryOrders: LaboratoryOrder[];
  studyOrders: StudyOrder[];
  compact?: boolean;
};

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function ClinicalOrdersHistory({ laboratoryOrders, studyOrders, compact = false }: Props) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function download(kind: "laboratory" | "study", id: number) {
    const key = `${kind}:${id}`;
    setBusy(key);
    setError("");
    try {
      const base = kind === "laboratory" ? "laboratory-orders" : "study-orders";
      const response = await api.get<Blob>(`/${base}/${id}/pdf`, { responseType: "blob" });
      saveBlob(response.data, `${kind === "laboratory" ? "orden-laboratorio" : "orden-estudios"}-${id}.pdf`);
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "No fue posible descargar la orden clínica.");
    } finally {
      setBusy("");
    }
  }

  if (!laboratoryOrders.length && !studyOrders.length) return null;

  return <div className={compact ? "space-y-2" : "rounded-xl border border-cyan-200 bg-cyan-50/40 p-4"}>
    {!compact && <div><h4 className="font-semibold text-cyan-950">Órdenes clínicas estructuradas</h4><p className="text-xs text-cyan-700">Laboratorios, estudios y procedimientos conservados con su contexto original.</p></div>}
    <div className={`${compact ? "" : "mt-3"} space-y-2`}>
      {laboratoryOrders.map((order) => <article key={`lab-${order.id}`} className="rounded-lg border bg-white p-3 text-sm">
        <div className="flex items-start justify-between gap-2"><p className="font-semibold">Laboratorio #{order.id}</p><button type="button" onClick={() => void download("laboratory", order.id)} disabled={Boolean(busy)} className="text-xs font-semibold text-cyan-700 disabled:opacity-40">{busy === `laboratory:${order.id}` ? "Generando..." : "PDF"}</button></div>
        <ul className="mt-1 list-disc pl-4">{order.items.map((item) => <li key={item.id}>{item.test_name}</li>)}</ul>
        {order.notes && <p className="mt-1 text-xs text-slate-600">Observaciones: {order.notes}</p>}
      </article>)}
      {studyOrders.map((order) => <article key={`study-${order.id}`} className="rounded-lg border bg-white p-3 text-sm">
        <div className="flex items-start justify-between gap-2"><p className="font-semibold">Estudios/procedimientos #{order.id}</p><button type="button" onClick={() => void download("study", order.id)} disabled={Boolean(busy)} className="text-xs font-semibold text-indigo-700 disabled:opacity-40">{busy === `study:${order.id}` ? "Generando..." : "PDF"}</button></div>
        <ul className="mt-1 list-disc pl-4">{order.items.map((item) => <li key={item.id}>{item.study_name}{item.region_description ? ` · ${item.region_description}` : ""}</li>)}</ul>
        {order.notes && <p className="mt-1 text-xs text-slate-600">Observaciones: {order.notes}</p>}
      </article>)}
    </div>
    {error && <div role="alert" className="mt-2 rounded bg-red-50 p-2 text-xs text-red-700">{error}</div>}
  </div>;
}
