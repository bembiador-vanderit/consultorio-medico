export type AppointmentStatus = "scheduled" | "confirmed" | "completed" | "cancelled" | "no_show";
export type Appointment = {
  id: number; patient_id: number; doctor_id: number; center_id: number | null;
  appointment_date: string; appointment_time: string;
  reason: string | null; status: AppointmentStatus; notes: string | null;
  patient_name: string; doctor_name: string; center_name: string | null; center_city: string | null;
  created_at: string; updated_at: string;
};
export type AppointmentInput = {
  patient_id: number;
  doctor_id: number | null;
  center_id: number | null;
  appointment_date: string;
  appointment_time: string;
  reason: string | null;
  status: AppointmentStatus;
  notes: string | null;
};
