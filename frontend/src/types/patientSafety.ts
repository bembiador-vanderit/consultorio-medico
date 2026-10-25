export const safetyTypes = { allergy: "Alergia", adverse_reaction: "Reacción adversa", contraindication: "Contraindicación", intolerance_avoid: "Intolerancia / Evitar" };
export const safetySeverities = { unknown: "Desconocida", mild: "Leve", moderate: "Moderada", severe: "Severa", critical: "Crítica" };
export const safetyStatuses = { active: "Activo", inactive: "Inactivo", entered_in_error: "Registrado por error" };
export const safetySources = { patient_reported: "Referido por paciente", family_reported: "Referido por familiar", prior_documentation: "Documentado previamente", observed_during_care: "Observado durante atención", physician_confirmed: "Confirmado por médico" };
export type SafetyContent = {
  entry_type: keyof typeof safetyTypes;
  substance_or_agent: string;
  reaction_description: string;
  severity: keyof typeof safetySeverities;
  status: keyof typeof safetyStatuses;
  onset_date: string | null;
  notes: string | null;
  source_type: keyof typeof safetySources;
  source_description: string | null;
};
export type PatientSafetyEntry = SafetyContent & {
  id:number; patient_id:number; organization_id:number; clinical_history_id:number|null;
  recorded_by_user_id:number; updated_by_user_id:number; recorded_by_name:string; updated_by_name:string;
  recorded_at:string; updated_at:string; revision:number;
};
