export type User = {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  primary_specialty_id?: number | null;
  specialty_ids?: number[];
  specialty_names?: string[];
};
