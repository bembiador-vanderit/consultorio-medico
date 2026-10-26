export type InsuranceCompany = { id: number; name: string; code: string | null; is_active: boolean; created_at: string };
export type InsurancePlan = { id: number; insurance_company_id: number; name: string; code: string | null; description: string | null; is_active: boolean };
export type PatientInsurance = {
  id: number; insurance_company_id: number; insurance_company_name: string; member_number: string;
  plan_id: number | null; plan_name: string | null; policy_holder: string | null; relationship_to_holder: string | null;
  valid_from: string | null; valid_until: string | null; administrative_notes: string | null;
  is_primary: boolean; is_active: boolean; created_at: string;
};
export type AppointmentInsuranceCoverage = {
  id: number; appointment_id: number; patient_insurance_id: number | null;
  insurance_snapshot: { company_name?: string; plan_name?: string; member_number?: string };
  service: string; currency: string; base_amount: string; covered_amount: string; patient_copay: string;
  expected_insurer_balance: string; authorization_status: string; authorization_number: string | null;
  authorized_at: string | null; authorized_amount: string | null; authorization_notes: string | null;
  notes: string | null; revision: number; updated_at: string;
};
