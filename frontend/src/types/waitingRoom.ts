export type WaitingRoom = {
  id: number; center_id: number; name: string; code: string | null; description: string | null;
  is_active: boolean; sort_order: number; created_at: string; updated_at: string;
  queue_lines: { id: number; name: string; prefix: string; provider_name: string; specialty_id: number | null }[];
  secretaries: { user_id: number; full_name: string }[];
  displays: { id: number; name: string; is_active: boolean }[];
};
