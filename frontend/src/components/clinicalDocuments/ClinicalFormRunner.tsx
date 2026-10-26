import { useState, type CSSProperties } from "react";
import type { ClinicalField, ClinicalFormDefinition } from "../../types/clinicalForm";
import "./clinicalFormRunner.css";

type Props = { definition: ClinicalFormDefinition; values: Record<string, string>;
  profile?: Record<string, string | null> | null; documentDate: string;
  onChange: (key: string, value: string) => void; readOnly: boolean;
  administrativeOnly?: boolean };

const bindings: Record<string, string> = {
  "patient.full_name": "patient_name", "patient.birth_date": "date_of_birth", "patient.age": "age_at_document",
  "patient.sex": "sex", "patient.document": "document_number", "patient.phone": "phone",
  "patient.address": "address", "patient.insurance": "insurance_company",
  "doctor.display_name": "doctor_name", "doctor.specialty": "doctor_specialty", "center.name": "center_name",
  "document.created_at": "created_at",
};

function hasValidLayout(field: ClinicalField) {
  return Number.isInteger(field.width) && field.width > 0 && field.width <= 12
    && Number.isInteger(field.row) && field.row > 0 && Number.isInteger(field.column) && field.column > 0
    && Number.isInteger(field.colspan) && field.colspan > 0 && field.column + field.colspan <= 13;
}

type FieldLayout = "designed" | "default" | "legacy";

function sectionLayout(fields: ClinicalField[]): FieldLayout {
  if (!fields.every(hasValidLayout)) return "legacy";
  // Untouched designer defaults carry no intentional field coordinates.
  return fields.every((field) => field.column === 1 && field.colspan === 12
    && field.width === 12 && field.row === field.sort_order) ? "default" : "designed";
}

function isFullWidth(field: ClinicalField) {
  return ["divider", "section_title", "static_text", "signature_placeholder"].includes(field.type);
}

function isBinary(field: ClinicalField) {
  return field.type === "yes_no" || field.type === "checkbox";
}

function fieldStyle(field: ClinicalField, layout: FieldLayout, fields: ClinicalField[], index: number): CSSProperties {
  const full = isFullWidth(field);
  // Unspecified narrative pairs share a desktop row. An isolated narrative keeps
  // the entire row; explicit designer spans (including text_long) take precedence.
  const narrativePair = field.type === "text_long"
    && (fields[index - 1]?.type === "text_long" || fields[index + 1]?.type === "text_long");
  const desktopSpan = full || layout === "legacy" ? 12 : layout === "designed" ? Math.min(field.colspan, field.width)
    : field.type === "text_long" ? narrativePair ? 6 : 12
      : ["yes_no", "checkbox", "integer", "decimal", "date", "time"].includes(field.type) ? 3
      : field.type === "text_short" && field.label.length <= 12 ? 3
        : ["text_short", "single_select", "multi_select"].includes(field.type) ? 6 : 12;
  const mobileSpan = full || field.type === "text_long" || layout === "legacy" || desktopSpan > 6
    || ["date", "time", "single_select", "multi_select", "patient_field", "doctor_field", "calculated"].includes(field.type)
    || (field.type === "text_short" && desktopSpan > 3) ? 2 : 1;
  return {
    "--desktop-column": layout === "designed" && !full ? field.column : "auto",
    "--desktop-span": desktopSpan,
    "--tablet-span": desktopSpan <= 4 ? 4 : desktopSpan <= 6 ? 6 : 12,
    "--mobile-span": mobileSpan,
  } as CSSProperties;
}

function renderFields(fields: ClinicalField[], layout: FieldLayout, values: Record<string, string>,
  profile: Props["profile"], documentDate: string, onChange: Props["onChange"], readOnly: boolean) {
  return fields.map((field, index) => <div key={field.key} className="clinical-form-field min-w-0" data-field-key={field.key} data-field-type={field.type}
    data-long-label={isBinary(field) && field.label.split(/\s+/).some((word) => word.length > 12) ? "true" : undefined} style={fieldStyle(field, layout, fields, index)}>
    <FormInput field={field} value={field.data_binding === "document.date" ? documentDate : field.data_binding ? profile?.[bindings[field.data_binding]] ?? "" : values[field.key] ?? field.default_value ?? ""}
      onChange={(value) => onChange(field.key, value)} readOnly={readOnly || field.read_only || Boolean(field.data_binding)} />
  </div>);
}

export default function ClinicalFormRunner({ definition, values, profile, documentDate, onChange, readOnly, administrativeOnly = false }: Props) {
  const pages = [...definition.pages].sort((a, b) => a.page_number - b.page_number);
  const [pageNumber, setPageNumber] = useState(pages[0]?.page_number ?? 1);
  const page = pages.find((item) => item.page_number === pageNumber) ?? pages[0];
  if (!page) return <p>Esta plantilla no contiene páginas.</p>;
  const sections = page.sections.slice().sort((a, b) => a.sort_order - b.sort_order).map((section) => {
    const fields = section.fields.filter((field) => field.visible && (!administrativeOnly || field.editable_by === "administrative"));
    const layout = sectionLayout(fields);
    const ordered = fields.slice().sort((a, b) => layout === "legacy"
      ? a.sort_order - b.sort_order : a.row - b.row || a.column - b.column || a.sort_order - b.sort_order);
    const firstNote = ordered.findIndex((field) => !isBinary(field));
    const binaryCount = firstNote < 0 ? ordered.length : firstNote;
    const binaryBlock = layout === "default" && binaryCount > 1
      && ordered.slice(binaryCount).every((field) => field.type === "text_long");
    return { ...section, layout, ordered, binaryBlock, binaryCount, paired: false };
  });
  // Sections have no row/column metadata in V1. Only adjacent, unspecified
  // binary blocks may share a row; explicitly designed sections remain intact.
  for (let index = 0; index < sections.length - 1; index++) {
    if (sections[index].binaryBlock && sections[index + 1].binaryBlock) {
      sections[index].paired = sections[index + 1].paired = true;
      index++;
    }
  }
  return <div className="clinical-form-runner min-w-0" data-clinical-form-runner>
    <nav className="clinical-form-page-nav mb-3 flex flex-wrap gap-2" aria-label="Páginas de la proforma">{pages.map((item) => <button
      key={item.page_number} type="button" aria-current={item.page_number === page.page_number ? "page" : undefined}
      className={`rounded-md border px-3 py-2 text-sm ${item.page_number === page.page_number ? "border-teal-700 bg-teal-50 font-semibold" : ""}`}
      onClick={() => setPageNumber(item.page_number)}>Página {item.page_number}</button>)}</nav>
    <div className="clinical-form-paper rounded-lg border bg-white p-3 sm:p-5" style={{ borderTopColor: definition.appearance.primary_color, borderTopWidth: 4 }}>
      <header className="clinical-form-paper-header mb-5 border-b pb-3 text-center">
        {definition.appearance.show_logo && definition.appearance.logo_data && <img src={definition.appearance.logo_data} alt="Logo de la plantilla" className="mx-auto mb-2 max-h-16 max-w-32 object-contain" />}
        {definition.appearance.center_heading && <p className="font-semibold">{definition.appearance.center_heading}</p>}
        {definition.appearance.doctor_heading && <p>{definition.appearance.doctor_heading}</p>}
        {definition.appearance.specialty_heading && <p className="text-sm">{definition.appearance.specialty_heading}</p>}
        <h5 className="mt-2 text-lg font-bold">{definition.appearance.header}</h5>
        {definition.appearance.subtitle && <p className="text-sm">{definition.appearance.subtitle}</p>}
      </header>
      <p className="mb-3 text-sm text-slate-600">{profile?.patient_name ?? "Paciente"} · {documentDate} · {page.title || `Página ${page.page_number}`}</p>
      <div className="clinical-form-sections">{sections.map((section) => {
        const { layout, ordered, binaryBlock, binaryCount, paired } = section;
        const rows = layout === "designed" ? [...new Set(ordered.map((field) => field.row))] : [];
        return <section key={section.key} className={`clinical-form-section${paired ? " clinical-form-section--paired" : ""}${binaryBlock && !paired ? " clinical-form-section--split" : ""}`} data-section-key={section.key}>
          <h6 className="clinical-form-section-title mb-3 border-b pb-1 font-semibold uppercase text-slate-800">{section.title}</h6>
          {binaryBlock ? <div className="clinical-form-section-body" data-layout={layout}>
            <div className="clinical-form-binary-fields">{renderFields(ordered.slice(0, binaryCount), layout, values, profile, documentDate, onChange, readOnly)}</div>
            {ordered.length > binaryCount && <div className="clinical-form-field-area"><div className="clinical-form-fields">
              {renderFields(ordered.slice(binaryCount), layout, values, profile, documentDate, onChange, readOnly)}
            </div></div>}
          </div> : <div className="clinical-form-field-area">{layout === "designed" ? <div className="clinical-form-rows" data-layout={layout}>{rows.map((row) => <div key={row} className="clinical-form-fields" data-row={row}>
            {renderFields(ordered.filter((field) => field.row === row), layout, values, profile, documentDate, onChange, readOnly)}
          </div>)}</div> : <div className="clinical-form-fields" data-layout={layout}>
            {renderFields(ordered, layout, values, profile, documentDate, onChange, readOnly)}
          </div>}</div>}
        </section>;
      })}</div>
      {definition.appearance.footer && <footer className="border-t pt-2 text-xs text-slate-500">{definition.appearance.footer}</footer>}
    </div>
  </div>;
}

function FormInput({ field, value, onChange, readOnly }: { field: ClinicalField; value: string; onChange: (value: string) => void; readOnly: boolean }) {
  const label = field.label_uppercase ? field.label.toUpperCase() : field.label;
  if (field.type === "divider") return <hr />;
  if (field.type === "section_title") return <strong className="block">{label}</strong>;
  if (field.type === "static_text") return <p className="text-sm">{label}</p>;
  if (field.type === "signature_placeholder") return <div className="mt-5 border-t pt-1 text-sm">{label}</div>;
  const base = "mt-1 block w-full min-w-0 rounded-md border border-slate-300 p-2 text-slate-900 disabled:bg-slate-100";
  if (field.type === "yes_no" || field.type === "checkbox") return <fieldset className="clinical-binary text-sm"><legend className="font-medium">{label}{field.required ? " *" : ""}</legend>
    <div className="clinical-binary-options mt-1 flex flex-wrap gap-2">{(["yes", "no"] as const).map((option) => <button key={option} type="button" disabled={readOnly}
      aria-pressed={value === option} className={`clinical-binary-option clinical-binary-option--${option}`}
      onClick={() => onChange(value === option ? "" : option)}>{option === "yes" ? "Sí" : "No"}</button>)}</div></fieldset>;
  if (field.type === "single_select") return <label className="block text-sm font-medium">{label}{field.required ? " *" : ""}<select className={base} value={value} disabled={readOnly} aria-required={field.required} onChange={(event) => onChange(event.target.value)}><option value="">Seleccione</option>{field.options.map((option) => <option key={option}>{option}</option>)}</select></label>;
  if (field.type === "multi_select") return <fieldset className="text-sm"><legend className="font-medium">{label}{field.required ? " *" : ""}</legend>{field.options.map((option) => <label key={option} className="mr-3 inline-flex items-center gap-1"><input type="checkbox" disabled={readOnly} checked={value.split("|").includes(option)} onChange={(event) => {
    const items = new Set(value ? value.split("|") : []); if (event.target.checked) items.add(option); else items.delete(option); onChange([...items].join("|"));
  }} />{option}</label>)}</fieldset>;
  if (field.type === "text_long") return <label className="block text-sm font-medium">{label}{field.required ? " *" : ""}<textarea className={base} value={value} rows={3} maxLength={5000} disabled={readOnly} aria-required={field.required} placeholder={field.placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
  const inputType = field.type === "integer" || field.type === "decimal" ? "number" : field.type === "date" ? "date" : field.type === "time" ? "time" : "text";
  return <label className="block text-sm font-medium">{label}{field.required ? " *" : ""}<div className="clinical-form-input-unit flex items-center gap-2"><input className={base} type={inputType} step={field.type === "decimal" ? "any" : field.type === "integer" ? "1" : undefined}
    value={value} disabled={readOnly} aria-required={field.required} placeholder={field.placeholder} maxLength={5000} onChange={(event) => onChange(event.target.value)} />{field.unit && <span className="text-xs text-slate-600">{field.unit}</span>}</div>{field.help_text && <small className="text-slate-500">{field.help_text}</small>}</label>;
}
