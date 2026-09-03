export type RequestedTest = {
  id: number;
  clinical_history_id: number;
  test_name: string;
};

export type ClinicalHistory = {
  id: number;
  patient_id: number;
  appointment_id: number | null;
  doctor_id: number | null;
  center_id: number | null;
  consultation_date: string;
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
  requested_tests: RequestedTest[];
  created_at: string;
  updated_at: string;
};

export type ClinicalHistoryInput = Omit<
  ClinicalHistory,
  "id" | "patient_id" | "appointment_id" | "doctor_id" | "center_id" | "created_at" | "updated_at" | "requested_tests"
> & {
  appointment_id?: number | null;
  requested_tests?: string;
};
