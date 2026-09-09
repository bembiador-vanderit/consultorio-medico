export type LaboratoryTest = {
  id: number;
  code: string | null;
  name: string;
  category: string;
  is_active: boolean;
  sort_order: number;
};

export type LaboratoryOrderItem = {
  id: number;
  laboratory_test_id: number;
  test_code: string | null;
  test_name: string;
  test_category: string;
  custom_note: string | null;
};

export type LaboratoryOrder = {
  id: number;
  clinical_history_id: number;
  patient_name: string;
  doctor_name: string;
  center_name: string | null;
  specialty_name: string;
  status: "ordered";
  notes: string | null;
  created_at: string;
  items: LaboratoryOrderItem[];
};

export type MedicalStudy = {
  id: number;
  specialty_id: number;
  anatomical_region_id: number | null;
  name: string;
  category: string;
  is_active: boolean;
};

export type StudyOrderItem = {
  id: number;
  medical_study_id: number;
  modality: string;
  study_name: string;
  region_description: string | null;
  contrast: "yes" | "no" | "not_applicable";
  clinical_notes: string | null;
};

export type StudyOrder = {
  id: number;
  clinical_history_id: number;
  patient_name: string;
  doctor_name: string;
  center_name: string | null;
  specialty_name: string;
  status: "ordered";
  notes: string | null;
  created_at: string;
  items: StudyOrderItem[];
};
