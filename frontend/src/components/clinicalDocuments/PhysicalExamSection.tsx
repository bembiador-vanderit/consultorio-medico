import { physicalExamFields } from "./fields";

type Props = { values: Record<string, string>; onChange: (key: string, value: string) => void; readOnly?: boolean };

export default function PhysicalExamSection({ values, onChange, readOnly = false }: Props) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2" data-physical-exam-section>
    {physicalExamFields.map(([key, label]) => <label key={key} className="min-w-0 text-sm font-medium text-slate-700">
      <span>{label}</span>
      <textarea className="mt-1 block w-full min-w-0 rounded-md border border-slate-300 p-2 text-slate-900 disabled:bg-slate-100" rows={key === "corazon" || key === "pulmones" || key === "abdomen" ? 2 : 1} maxLength={5000} value={values[key] ?? ""} onChange={(event) => onChange(key, event.target.value)} disabled={readOnly} />
    </label>)}
  </div>;
}
