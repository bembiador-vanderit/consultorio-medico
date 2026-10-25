export type ClinicalFieldType = "text_short" | "text_long" | "integer" | "decimal" | "date" | "time" | "yes_no" | "single_select" | "multi_select" | "checkbox" | "patient_field" | "doctor_field" | "calculated" | "signature_placeholder" | "static_text" | "divider" | "section_title";
export type ClinicalField = {
  key: string; label: string; type: ClinicalFieldType; required: boolean; label_uppercase: boolean;
  placeholder: string; help_text: string; default_value: string | null; unit: string; options: string[];
  width: number; row: number; column: number; colspan: number; sort_order: number;
  visible: boolean; printable: boolean; read_only: boolean; editable_by: "clinical" | "administrative";
  data_binding: string | null; validation: Record<string, number>;
};
export type ClinicalSection = { key: string; title: string; sort_order: number; printable: boolean; fields: ClinicalField[] };
export type ClinicalPage = { page_number: number; title: string; orientation: "portrait" | "landscape"; page_size: "A4" | "Letter"; margins: { top: number; bottom: number; left: number; right: number }; sort_order: number; sections: ClinicalSection[] };
export type ClinicalFormDefinition = { appearance: {
  show_logo: boolean; logo_data: string | null; doctor_heading: string; specialty_heading: string;
  center_heading: string; header: string; subtitle: string; footer: string; primary_color: string;
  font: "Helvetica" | "Times-Roman" | "Courier"; font_size: number; density: "compact" | "normal" | "comfortable";
}; pages: ClinicalPage[] };
export type ClinicalTemplate = {
  id: number; name: string; code: string; description: string; document_type: "preoperative" | "physical_exam";
  status: "draft" | "published" | "retired"; current_version_id: number | null;
  current_version: number | null; draft_version_id: number | null; editable_version_id: number | null;
  definition: ClinicalFormDefinition | null; created_at: string; updated_at: string;
};
