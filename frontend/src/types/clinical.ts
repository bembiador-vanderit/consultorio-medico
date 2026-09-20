import type { AppointmentStatus } from "./appointment";

export type ClinicalHistoryStatus = "in_progress" | "completed";

export type ClinicalHistoryContent = {
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
};

export type RequestedTest = {
  id: number;
  clinical_history_id: number;
  test_name: string;
};

export type ClinicalAddendum = {
  id: number;
  clinical_history_id: number;
  author_user_id: number | null;
  author_name: string;
  reason: string | null;
  note: string;
  created_at: string;
};

export type ClinicalHistory = ClinicalHistoryContent & {
  patient_date_of_birth?: string;
  id: number;
  patient_id: number;
  appointment_id: number | null;
  doctor_id: number | null;
  center_id: number | null;
  specialty_id: number | null;
  specialty_name: string;
  doctor_name: string | null;
  center_name: string | null;
  status: ClinicalHistoryStatus;
  revision: number;
  completed_at: string | null;
  completed_by_id: number | null;
  requested_tests: RequestedTest[];
  created_at: string;
  updated_at: string;
};

export type ClinicalHistoryInput = Omit<
  ClinicalHistory,
  "patient_date_of_birth" | "id" | "patient_id" | "appointment_id" | "doctor_id" | "center_id" | "specialty_id" | "specialty_name" | "doctor_name" | "center_name" | "status" | "revision" | "completed_at" | "completed_by_id" | "created_at" | "updated_at" | "requested_tests"
> & {
  appointment_id?: number | null;
  requested_tests?: string;
};

export type ConsultationContext = {
  appointment_id: number;
  patient_id: number;
  doctor_id: number;
  center_id: number | null;
  specialty_id: number | null;
  specialty_name: string;
  appointment_date: string;
  appointment_time: string;
  appointment_reason: string | null;
  appointment_status: AppointmentStatus;
  patient_blood_type?: string | null;
  previous_consultations: ClinicalHistory[];
};

export type Diagnosis = {
  id: number;
  clinical_history_id: number;
  description: string;
  icd10_code: string | null;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
};

export type Prescription = {
  id: number;
  clinical_history_id: number;
  medication: string;
  presentation: string | null;
  dose: string | null;
  route: string | null;
  frequency: string | null;
  duration: string | null;
  quantity: number | null;
  instructions: string | null;
  created_at: string;
  updated_at: string;
};

export type PrescriptionInput = Omit<
  Prescription,
  "id" | "clinical_history_id" | "created_at" | "updated_at"
>;

export type VitalSigns = {
  id: number;
  clinical_history_id: number;
  systolic_pressure: number | null;
  diastolic_pressure: number | null;
  heart_rate: number | null;
  respiratory_rate: number | null;
  temperature_c: number | null;
  oxygen_saturation: number | null;
  weight_kg: number | null;
  height_cm: number | null;
  created_at: string;
  updated_at: string;
};

export type MedicalStudy = {
  id: number;
  specialty_id: number;
  anatomical_region_id: number | null;
  name: string;
  category: string;
  is_active: boolean;
  recommended_specialty_ids: number[];
};
