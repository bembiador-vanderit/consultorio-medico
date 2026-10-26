export const careTypes = { treating:"Tratante", consultant:"Interconsultor", specialist_followup:"Seguimiento especialista", primary:"Médico principal habitual" };
export const careStatuses = { active:"Activa", follow_up:"En seguimiento", historical:"Histórica", ended:"Finalizada" };
export const careOrigins = { consultation:"Consulta finalizada", administrative_assignment:"Asignación administrativa", referral:"Referencia", migration:"Importación histórica", emergency:"Emergencia", inpatient:"Hospitalización", interconsultation:"Interconsulta" };

export type PatientCareRelationship = {
  id:number; organization_id:number; patient_id:number; doctor_id:number;
  doctor_name:string; center_id:number|null; center_name:string|null;
  specialty_id:number|null; specialty_name:string|null; organization_name:string;
  relationship_type:keyof typeof careTypes; status:keyof typeof careStatuses; origin:keyof typeof careOrigins;
  started_at:string; first_seen_at:string|null; last_seen_at:string|null; ended_at:string|null;
  created_from_clinical_history_id:number|null; last_clinical_history_id:number|null;
  created_by_user_id:number; updated_by_user_id:number; created_at:string; updated_at:string; revision:number;
};
