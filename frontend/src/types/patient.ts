export type PatientDemographics = {
  document_type?: string | null;
  document_number?: string | null;
  home_phone?: string | null;
  registered_sex?: string | null;
  blood_type?: string | null;
  address?: string | null;
  country_code?: string | null;
  country_name?: string | null;
  territorial_unit_id?: number | null;
  territorial_path?: Array<{ level:number; key:string; label:string; unit_id:number; name:string }>;
  sector_locality?: string | null;
  province?: string | null;
  nationality?: string | null;
  occupation?: string | null;
  emergency_contact_name?: string | null;
  emergency_contact_relationship?: string | null;
  emergency_contact_mobile?: string | null;
  emergency_contact_home_phone?: string | null;
  guardian_name?: string | null;
  guardian_relationship?: string | null;
  guardian_mobile?: string | null;
  guardian_home_phone?: string | null;
  locality_id?: number | null;
  locality_name?: string | null;
};

export type Patient = PatientDemographics & {
  id: number;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  phone: string | null;
  email: string | null;
  created_at: string;
  selection_token?: string;
};
