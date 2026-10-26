export type QueueLine = {
  id: number; center_id: number; doctor_id: number; specialty_id: number | null;
  name: string; prefix: string; is_active: boolean; call_on_consultation_start: boolean; doctor_name: string; center_name: string;
  waiting_room_id?: number | null;
};

export type QueueTicket = {
  id: number; queue_line_id: number; appointment_id: number; patient_id: number;
  doctor_id: number; center_id: number; specialty_id: number | null;
  service_date: string; sequence_number: number; public_code: string;
  source: "arrival"; status: "waiting" | "called" | "in_service" | "completed" | "no_response" | "left";
  arrived_at: string; ticket_issued_at: string; arrival_registered_by: number; ticket_issued_by: number;
  first_called_at: string | null; last_called_at: string | null; called_by_user_id: number | null; call_count: number;
  consultation_started_at: string | null; consultation_started_by_user_id: number | null;
  consultation_finished_at: string | null; consultation_finished_by_user_id: number | null;
  left_at: string | null; left_by_user_id: number | null;
};

export type QueueTicketEvent = {
  id: number; queue_ticket_id: number;
  event_type: "ARRIVED" | "ISSUED" | "CALLED" | "RECALLED" | "SERVICE_STARTED" | "SERVICE_COMPLETED" | "NO_RESPONSE" | "LEFT";
  occurred_at: string; actor_user_id: number | null; call_source?: "manual" | "automatic" | null; created_at: string;
};

export type QueueCallPolicy = {
  queue_line_id: number; center_id: number;
  call_mode: "manual" | "assisted" | "automatic";
  preparation_seconds: number;
  start_consultation_can_call: boolean;
};

export type NextCallState = {
  queue_line_id: number; call_mode: QueueCallPolicy["call_mode"];
  preparation_seconds: number; provider_paused: boolean;
  current_in_service_ticket_id: number | null;
  next_waiting_ticket_id: number | null;
  next_waiting_public_code: string | null;
  last_service_completed_at: string | null;
  ready_at: string | null; server_now: string;
  ready: boolean; can_call: boolean; block_reason: string | null;
};
