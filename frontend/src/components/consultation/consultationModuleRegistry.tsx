import type { Dispatch, ReactNode, SetStateAction } from "react";

import ClinicalOrdersSection from "../clinical/ClinicalOrdersSection";
import type { Appointment } from "../../types/appointment";
import type {
  ClinicalHistory,
  ClinicalHistoryContent,
  ConsultationContext,
  Diagnosis,
  Prescription,
  VitalSigns,
  WorkspaceModule,
} from "../../types/clinical";
import type { User } from "../../types/user";
import AnamnesisModule from "./AnamnesisModule";
import DiagnosesModule from "./DiagnosesModule";
import PrescriptionsModule from "./PrescriptionsModule";
import VitalSignsModule from "./VitalSignsModule";

export const consultationModuleKeys = [
  "core.anamnesis",
  "core.vital-signs",
  "core.diagnoses",
  "core.prescriptions",
  "core.clinical-orders",
] as const;

export type ConsultationModuleKey = typeof consultationModuleKeys[number];

export const defaultWorkspaceModules: WorkspaceModule[] = consultationModuleKeys.map((key, index) => ({
  key,
  label: {
    "core.anamnesis": "Historia de la consulta",
    "core.vital-signs": "Signos vitales",
    "core.diagnoses": "Diagnósticos",
    "core.prescriptions": "Recetas",
    "core.clinical-orders": "Órdenes clínicas",
  }[key],
  position: index + 1,
  required: true,
}));

export type ConsultationModuleRenderContext = {
  appointment: Appointment;
  bootstrapVersion: number;
  context: ConsultationContext;
  saved: ClinicalHistory | null;
  completed: boolean;
  saving: boolean;
  vitalSigns: VitalSigns | null;
  loadingVitalSigns: boolean;
  setVitalSigns: Dispatch<SetStateAction<VitalSigns | null>>;
  diagnoses: Diagnosis[];
  setDiagnoses: Dispatch<SetStateAction<Diagnosis[]>>;
  prescriptions: Prescription[];
  setPrescriptions: Dispatch<SetStateAction<Prescription[]>>;
  setError: Dispatch<SetStateAction<string>>;
  currentUser: User | null;
  downloadingPrescriptionPdf: boolean;
  downloadPrescriptionPdf: () => Promise<void>;
  saveHistory: (form: ClinicalHistoryContent) => Promise<void>;
  onAnamnesisDirty: (dirty: boolean) => void;
  onVitalSignsDirty: (dirty: boolean) => void;
  onDiagnosesDirty: (dirty: boolean) => void;
  onPrescriptionsDirty: (dirty: boolean) => void;
  onOrdersDirty: (dirty: boolean) => void;
};

type ConsultationModuleDefinition = {
  key: ConsultationModuleKey;
  render: (renderContext: ConsultationModuleRenderContext) => ReactNode;
};

export const consultationModuleRegistry: Record<ConsultationModuleKey, ConsultationModuleDefinition> = {
  "core.anamnesis": {
    key: "core.anamnesis",
    render: (item) => <AnamnesisModule
      key={`anamnesis:${item.appointment.id}:${item.bootstrapVersion}`}
      patientDateOfBirth={item.appointment.patient_date_of_birth}
      episodeId={item.appointment.id}
      appointmentReason={item.context.appointment_reason ?? item.appointment.reason}
      history={item.saved}
      completed={item.completed}
      saving={item.saving}
      onSave={item.saveHistory}
      onDirtyChange={item.onAnamnesisDirty}
    />,
  },
  "core.vital-signs": {
    key: "core.vital-signs",
    render: (item) => <VitalSignsModule
      key={`vitals:${item.appointment.id}:${item.bootstrapVersion}`}
      episodeId={item.appointment.id}
      historyId={item.saved?.id ?? null}
      vitalSigns={item.vitalSigns}
      completed={item.completed}
      loading={item.loadingVitalSigns}
      onSaved={item.setVitalSigns}
      onDirtyChange={item.onVitalSignsDirty}
    />,
  },
  "core.diagnoses": {
    key: "core.diagnoses",
    render: (item) => <DiagnosesModule
      key={`diagnoses:${item.appointment.id}:${item.saved?.id ?? "new"}:${item.bootstrapVersion}`}
      episodeId={item.appointment.id}
      historyId={item.saved?.id ?? null}
      diagnoses={item.diagnoses}
      completed={item.completed}
      onChange={item.setDiagnoses}
      onError={item.setError}
      onDirtyChange={item.onDiagnosesDirty}
    />,
  },
  "core.prescriptions": {
    key: "core.prescriptions",
    render: (item) => <PrescriptionsModule
      key={`prescriptions:${item.appointment.id}:${item.saved?.id ?? "new"}:${item.bootstrapVersion}`}
      episodeId={item.appointment.id}
      historyId={item.saved?.id ?? null}
      prescriptions={item.prescriptions}
      completed={item.completed}
      onChange={item.setPrescriptions}
      onError={item.setError}
      downloadingPrescriptionPdf={item.downloadingPrescriptionPdf}
      downloadPrescriptionPdf={item.downloadPrescriptionPdf}
      onDirtyChange={item.onPrescriptionsDirty}
    />,
  },
  "core.clinical-orders": {
    key: "core.clinical-orders",
    render: (item) => item.saved
      ? <ClinicalOrdersSection
          key={`orders:${item.saved.id}:${item.bootstrapVersion}`}
          historyId={item.saved.id}
          specialtyId={item.saved.specialty_id}
          completed={item.completed}
          allowAdditional={Boolean(
            item.completed
            && item.currentUser?.is_active
            && item.currentUser.roles.includes("doctor")
            && item.saved.doctor_id === item.currentUser.id
          )}
          onDirtyChange={item.onOrdersDirty}
        />
      : <div className="rounded-xl border border-dashed bg-white p-6 text-sm text-slate-600 shadow-sm">Guarda primero la consulta para crear órdenes estructuradas de laboratorio, estudios o procedimientos.</div>,
  },
};

export function isKnownConsultationModule(key: string): key is ConsultationModuleKey {
  return Object.prototype.hasOwnProperty.call(consultationModuleRegistry, key);
}
