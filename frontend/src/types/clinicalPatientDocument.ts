import type { ClinicalField, ClinicalFormDefinition } from "./clinicalForm";

export type ClinicalDocumentKind = "preoperative" | "physical_exam";
export type ClinicalDocumentStatus = "draft" | "pending_evaluation" | "completed" | "signed";
export type ClinicalPatientDocument = {
  kind: ClinicalDocumentKind; id: number; patient_id: number; doctor_id: number; center_id: number;
  appointment_id: number | null; clinical_history_id: number | null;
  document_date: string; status: ClinicalDocumentStatus; revision: number;
  created_by_user_id: number; created_by_name: string; last_updated_by_user_id: number;
  signed_by_user_id: number | null; signed_at: string | null; created_at: string; updated_at: string;
  patient_name: string; doctor_name: string; center_name: string;
  values: Record<string, string> | null; patient_profile: Record<string, string | null> | null;
  template_id?: number | null; template_version_id?: number | null;
  template_definition?: ClinicalFormDefinition | null; template_admin_fields?: ClinicalField[] | null;
  template_source?: "versioned" | "legacy_0055";
};
