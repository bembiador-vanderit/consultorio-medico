import { useEffect, useState } from "react";
import { Alert, FormField, FormSection, Input, Select } from "../../ui";
import { api } from "../../services/api";
import type { PatientDemographics } from "../../types/patient";

export const documentLabels: Record<string, string> = { cedula: "Cédula", passport: "Pasaporte", other: "Otro" };
export const sexLabels: Record<string, string> = { female: "Femenino", male: "Masculino", other: "Otro", unknown: "Desconocido" };
export const bloodTypes = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
type Section = "personal" | "clinical-basic" | "clinical-contacts";
type Props = { value: PatientDemographics; onChange: (value: PatientDemographics) => void; section: Section };
type Locality = { id: number; name: string };

export default function PatientDemographicFields({ value, onChange, section }: Props) {
  const [localities, setLocalities] = useState<Locality[]>([]);
  const [localityError, setLocalityError] = useState(false);

  useEffect(() => {
    if (section !== "personal") return;
    let active = true;
    api.get<Locality[]>("/patients/localities")
      .then(({ data }) => { if (active) setLocalities(data); })
      .catch(() => { if (active) setLocalityError(true); });
    return () => { active = false; };
  }, [section]);

  const change = (key: keyof PatientDemographics, next: string) => onChange({ ...value, [key]: next || null });
  const input = (key: keyof PatientDemographics, label: string, maxLength = 100, type = "text") =>
    <FormField key={key} label={label}><Input type={type} maxLength={maxLength} value={value[key] ?? ""} onChange={(event) => change(key, event.target.value)} /></FormField>;

  if (section === "clinical-basic") return <FormSection title="Datos clínicos básicos" description="Datos registrados en la ficha del paciente.">
    <FormField label="Sexo registrado para fines clínicos">
      <Select value={value.registered_sex ?? ""} onChange={(event) => change("registered_sex", event.target.value)}>
        <option value="">Sin registrar</option>
        {Object.entries(sexLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </Select>
    </FormField>
    <FormField label="Tipo sanguíneo" description="Declarado/registrado; no equivale a confirmación de laboratorio.">
      <Select value={value.blood_type ?? ""} onChange={(event) => change("blood_type", event.target.value)}>
        <option value="">Desconocido / sin registrar</option>
        {bloodTypes.map((type) => <option key={type}>{type}</option>)}
      </Select>
    </FormField>
  </FormSection>;

  if (section === "clinical-contacts") return <>
    <FormSection title="Contacto de emergencia" description="Opcional.">
      {input("emergency_contact_name", "Nombre del contacto de emergencia", 150)}
      {input("emergency_contact_relationship", "Parentesco del contacto de emergencia")}
      {input("emergency_contact_mobile", "Celular del contacto de emergencia", 30, "tel")}
      {input("emergency_contact_home_phone", "Casa del contacto de emergencia", 30, "tel")}
    </FormSection>
    <FormSection title="Tutor / responsable" description="Opcional; registre los datos cuando corresponda.">
      {input("guardian_name", "Nombre del tutor / responsable", 150)}
      {input("guardian_relationship", "Parentesco del tutor / responsable")}
      {input("guardian_mobile", "Celular del tutor / responsable", 30, "tel")}
      {input("guardian_home_phone", "Casa del tutor / responsable", 30, "tel")}
    </FormSection>
  </>;

  return <>
    <FormSection title="Dirección">
      {input("address", "Dirección", 500)}
      {input("province", "Provincia")}
      <FormField label="Municipio / localidad">
        <Select disabled={localityError} value={value.locality_id ?? ""} onChange={(event) => onChange({ ...value, locality_id: event.target.value ? Number(event.target.value) : null })}>
          <option value="">Sin registrar</option>
          {value.locality_id && !localities.some((item) => item.id === value.locality_id) && <option value={value.locality_id}>Localidad registrada (conservar)</option>}
          {localities.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </Select>
      </FormField>
      {localityError && <Alert tone="warning" title="Localidades no disponibles">Se conservará la localidad registrada. Puede guardar los otros datos.</Alert>}
    </FormSection>
    <FormSection title="Información adicional">
      {input("nationality", "Nacionalidad")}
      {input("occupation", "Ocupación / profesión", 150)}
    </FormSection>
  </>;
}
