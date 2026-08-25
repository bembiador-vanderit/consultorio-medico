export type ClinicalHistory = {
  id: number;
  patient_id: number;
  reason_for_visit: string | null;
  current_illness: string | null;
  personal_history: string | null;
  family_history: string | null;
  allergies: string | null;
  current_medications: string | null;
  previous_surgeries: string | null;
  chronic_conditions: string | null;
  habits: string | null;
  clinical_notes: string | null;
  created_at: string;
  updated_at: string;
};

export type ClinicalHistoryInput = Omit<
  ClinicalHistory,
  "id" | "patient_id" | "created_at" | "updated_at"
>;
