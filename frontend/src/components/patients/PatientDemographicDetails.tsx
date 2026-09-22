import type { Patient } from "../../types/patient";

export default function PatientDemographicDetails({ patient }: { patient: Patient }) {
  const structured = patient.territorial_path?.length ? patient.territorial_path : [];
  const rows: Array<[string, string | number | null | undefined]> = [
    ["Documento", patient.document_type && patient.document_number ? `${patient.document_type}: ${patient.document_number}` : null],
    ["Sexo registrado", patient.registered_sex], ["Tipo sanguíneo declarado/registrado", patient.blood_type],
    ["País", patient.country_name], ...structured.map(item => [item.label, item.name] as [string, string]),
    ["Sector / Localidad", patient.sector_locality], ["Dirección", patient.address],
    ...(structured.length ? [] : [["Provincia", patient.province], ["Municipio / localidad", patient.locality_name]] as Array<[string, string | null | undefined]>),
    ["Nacionalidad", patient.nationality], ["Ocupación / Profesión", patient.occupation],
    ["Teléfono de casa", patient.home_phone], ["Contacto de emergencia", patient.emergency_contact_name], ["Tutor / responsable", patient.guardian_name],
  ];
  return <dl className="patients-facts">{rows.filter(([, value]) => value).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}