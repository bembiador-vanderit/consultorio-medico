export type AppointmentStatus = "scheduled" | "confirmed" | "completed" | "cancelled" | "no_show";
export type Appointment = {
  id: number; patient_id: number; doctor_id: number; center_id: number | null; specialty_id: number | null;
  appointment_date: string; appointment_time: string | null; schedule_mode?: "timed" | "queue";
  daily_booking_order?: number | null;
  arrival_enabled?: boolean;
  arrived_at?: string | null;
  arrival_registered_by?: number | null;
  reason: string | null; status: AppointmentStatus; notes: string | null;
  patient_name: string; patient_phone: string | null; patient_date_of_birth: string; doctor_name: string; center_name: string | null; center_city: string | null;
  specialty_name: string;
  coverage_id: number | null; original_doctor_id: number | null; original_doctor_name: string | null;
  has_clinical_history: boolean;
  clinical_history_id: number | null;
  clinical_history_status: "in_progress" | "completed" | null;
  clinical_history_doctor_id: number | null;
  created_at: string; updated_at: string;
};
export type AppointmentInput = {
  patient_id: number;
  doctor_id: number | null;
  center_id: number | null;
  specialty_id: number | null;
  appointment_date: string;
  appointment_time: string | null;
  reason: string | null;
  status: AppointmentStatus;
  notes: string | null;
};
