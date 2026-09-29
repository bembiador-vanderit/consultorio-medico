export type User = {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  permissions?: string[];
  denied_permissions?: string[];
  primary_specialty_id?: number | null;
  specialty_ids?: number[];
  specialty_names?: string[];
  access_scope?: "tenant" | "platform";
  organization?: { id: number; name: string } | null;
  membership_state?: "active" | "suspended" | "invited" | null;
};
