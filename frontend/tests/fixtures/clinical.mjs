export const activeDoctor = {
  id: 12,
  email: "dra.prueba@example.test",
  full_name: "Dra. Prueba",
  is_active: true,
  roles: ["doctor"],
  primary_specialty_id: 4,
  specialty_ids: [4],
  specialty_names: ["Cardiología ficticia"],
};

export const appointmentScheduled = {
  id: 81,
  patient_id: 34,
  doctor_id: 12,
  center_id: 7,
  specialty_id: 4,
  appointment_date: "2026-09-16",
  appointment_time: "09:30:00",
  reason: "Control ficticio",
  status: "scheduled",
  notes: "Nota ficticia",
  patient_name: "Paciente de prueba",
  patient_date_of_birth: "1990-05-12",
  doctor_name: "Dra. Prueba",
  center_name: "Centro de prueba",
  center_city: "Santo Domingo",
  specialty_name: "Cardiología ficticia",
  coverage_id: null,
  original_doctor_id: null,
  original_doctor_name: null,
  has_clinical_history: false,
  clinical_history_id: null,
  clinical_history_status: null,
  clinical_history_doctor_id: null,
  created_at: "2026-09-01T08:00:00",
  updated_at: "2026-09-01T08:00:00",
};

export const appointmentConfirmed = {
  ...appointmentScheduled,
  id: 82,
  status: "confirmed",
};

export function clinicalHistory(overrides = {}) {
  return {
    id: 42,
    patient_id: 34,
    appointment_id: 81,
    doctor_id: 12,
    center_id: 7,
    specialty_id: 4,
    specialty_name: "Cardiología ficticia",
    doctor_name: "Dra. Prueba",
    center_name: "Centro de prueba",
    status: "in_progress",
    completed_at: null,
    completed_by_id: null,
    consultation_date: "2026-09-16",
    reason_for_visit: "Control ficticio",
    current_illness: "Evolución ficticia",
    personal_history: null,
    family_history: null,
    allergies: null,
    current_medications: null,
    previous_surgeries: null,
    chronic_conditions: null,
    habits: null,
    clinical_notes: "Notas ficticias",
    requested_tests: [],
    created_at: "2026-09-16T09:30:00",
    updated_at: "2026-09-16T09:30:00",
    ...overrides,
  };
}

export const clinicalHistoryInProgress = clinicalHistory();
export const clinicalHistoryCompleted = clinicalHistory({
  status: "completed",
  completed_at: "2026-09-16T10:00:00",
  completed_by_id: 12,
});

export const legacyClinicalHistory = clinicalHistory({
  id: 18,
  appointment_id: null,
  specialty_id: null,
  specialty_name: "No especificada (registro histórico)",
  status: "completed",
  completed_at: "2025-06-02T10:00:00",
  completed_by_id: 12,
  consultation_date: "2025-06-02",
  reason_for_visit: "Consulta histórica ficticia",
});

export const vitalSignsFixture = {
  id: 5,
  clinical_history_id: 42,
  systolic_pressure: 120,
  diastolic_pressure: 80,
  heart_rate: 72,
  respiratory_rate: null,
  temperature_c: null,
  oxygen_saturation: null,
  weight_kg: 68.5,
  height_cm: 167,
  created_at: "2026-09-16T09:35:00",
  updated_at: "2026-09-16T09:35:00",
};

export const diagnosisFixture = {
  id: 9,
  clinical_history_id: 42,
  description: "Diagnóstico ficticio",
  icd10_code: "Z00.0",
  is_primary: true,
  created_at: "2026-09-16T09:40:00",
  updated_at: "2026-09-16T09:40:00",
};

export const prescriptionFixture = {
  id: 11,
  clinical_history_id: 42,
  medication: "Medicamento ficticio",
  presentation: "Tableta",
  dose: "10 mg",
  route: "Oral",
  frequency: "Cada 24 horas",
  duration: "5 días",
  quantity: 5,
  instructions: null,
  created_at: "2026-09-16T09:45:00",
  updated_at: "2026-09-16T09:45:00",
};

export const requestedTestFixture = {
  id: 14,
  clinical_history_id: 42,
  test_name: "Estudio ficticio",
};

export const medicalStudyFixture = {
  id: 21,
  specialty_id: 4,
  anatomical_region_id: null,
  name: "Ecocardiograma ficticio",
  category: "study",
  is_active: true,
  recommended_specialty_ids: [4],
};

export const laboratoryTestFixture = {
  id: 31,
  code: "LAB-FICT",
  name: "Hemograma ficticio",
  category: "Laboratorio",
  is_active: true,
  sort_order: 1,
};
