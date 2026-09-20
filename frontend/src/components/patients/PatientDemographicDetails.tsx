import type { Patient } from "../../types/patient";
import { documentLabels, sexLabels } from "./PatientDemographicFields";

export default function PatientDemographicDetails({ patient }: { patient: Patient }) {
  const rows = [
    ["Documento", patient.document_number ? `${documentLabels[patient.document_type ?? ""] ?? "Documento"}: ${patient.document_number}` : null],
    ["Dirección", patient.address], ["Provincia", patient.province], ["Municipio / localidad", patient.locality_name],
    ["Nacionalidad", patient.nationality], ["Ocupación / profesión", patient.occupation],
    ["Teléfono de casa", patient.home_phone], ["Sexo registrado para fines clínicos", sexLabels[patient.registered_sex ?? ""]],
    ["Tipo sanguíneo declarado/registrado", patient.blood_type],
    ["Contacto de emergencia", patient.emergency_contact_name], ["Parentesco del contacto", patient.emergency_contact_relationship],
    ["Celular de emergencia", patient.emergency_contact_mobile], ["Casa de emergencia", patient.emergency_contact_home_phone],
    ["Tutor / responsable", patient.guardian_name], ["Parentesco del tutor", patient.guardian_relationship],
    ["Celular del tutor", patient.guardian_mobile], ["Casa del tutor", patient.guardian_home_phone],
  ];
  return <section aria-label="Identidad y demografía"><dl className="patients-facts">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "Sin registrar"}</dd></div>)}</dl><p className="atlas-help">El tipo sanguíneo registrado no equivale a confirmación de laboratorio.</p></section>;
}
