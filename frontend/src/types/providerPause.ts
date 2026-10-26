export type PauseReason = "ward_rounds" | "procedure" | "emergency" | "meeting" | "lunch" | "temporary_absence" | "other";

export type ProviderPause = {
  id: number;
  organization_id: number;
  center_id: number;
  doctor_id: number;
  reason: PauseReason;
  notes: string | null;
  planned_start_at: string | null;
  actual_started_at: string;
  actual_finished_at: string | null;
  started_by_user_id: number;
  finished_by_user_id: number | null;
  duration_seconds: number | null;
};
