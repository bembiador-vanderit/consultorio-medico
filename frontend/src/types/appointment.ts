export type AppointmentStatus = "scheduled" | "confirmed" | "completed" | "cancelled" | "no_show";
export type Appointment = {
  id: number; patient_id: number; doctor_id: number;
  appointment_date: string; appointment_time: string;
  reason: string | null; status: AppointmentStatus; notes: string | null;
  patient_name: string; doctor_name: string; created_at: string; updated_at: string;
};
export type AppointmentInput = Omit<Appointment, "id" | "doctor_id" | "patient_name" | "doctor_name" | "created_at" | "updated_at">;
