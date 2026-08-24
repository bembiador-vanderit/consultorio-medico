export type InsuranceCompany = {
  id: number;
  name: string;
  code: string | null;
  is_active: boolean;
  created_at: string;
};

export type PatientInsurance = {
  id: number;
  insurance_company_id: number;
  insurance_company_name: string;
  member_number: string;
  plan_name: string | null;
  is_primary: boolean;
  is_active: boolean;
  created_at: string;
};
