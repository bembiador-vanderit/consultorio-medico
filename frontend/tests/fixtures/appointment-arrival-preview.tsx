import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "../../src/index.css";
import { AppointmentArrivalAction } from "../../src/components/agenda/AppointmentArrivalAction";
import { AgendaAppointmentCard } from "../../src/components/agenda/AgendaAppointmentCard";
import { isoDate } from "../../src/components/agenda/agenda";
import { api } from "../../src/services/api";
import type { Appointment } from "../../src/types/appointment";
import type { User } from "../../src/types/user";

const initial = { id: 19, patient_id: 19, patient_name: "QA Piloto A", patient_phone: null,
  doctor_id: 3, center_id: 1, center_name: "QA CEMER", doctor_name: "Médico QA", specialty_id: 1,
  specialty_name: "Cardiología", appointment_date: isoDate(new Date()), appointment_time: "08:30:00",
  schedule_mode: "timed", status: "scheduled", arrival_enabled: true, arrived_at: null, has_clinical_history: false } as Appointment;
const actor = { id: 5, is_active: true, roles: ["secretary"], permissions: ["patients:access"] } as User;
let saved: Appointment = initial;
api.defaults.adapter = async config => {
  if (config.method !== "post" || config.url !== "/appointments/19/arrival") throw new Error("Fixture: petición no permitida");
  saved = { ...initial, arrived_at: new Date().toISOString(), arrival_registered_by: 5 };
  return { config, status: 200, statusText: "OK", headers: {}, data: saved };
};
function Preview() {
  const [appointment, setAppointment] = useState(initial);
  return <main style={{ maxWidth: 960, margin: "24px auto", padding: 16 }}>
    <p role="note">Fixture visual aislado · No registra datos en la base oficial.</p>
    <h1>Agenda · Llegada Por hora</h1>
    <p>Fecha actual · CEMER · Cardiología</p>
    <AgendaAppointmentCard appointment={appointment} variant="day" onSelect={() => {}}
      arrivalAction={<AppointmentArrivalAction appointment={appointment} user={actor} canAccessPair presentation="row"
        onChanged={() => setAppointment(saved)} />} />
    <p>La modalidad sigue Por hora. No se emite número de turno.</p>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
