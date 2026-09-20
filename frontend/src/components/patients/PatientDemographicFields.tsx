import { useEffect, useState, type ComponentProps } from "react";
import { Alert, FormField, FormSection, Input, Select } from "../../ui";
import { api } from "../../services/api";
import type { PatientDemographics } from "../../types/patient";
import { PatientFormIcon, type PatientFormIconName } from "./PatientFormIcon";

export const documentLabels: Record<string, string> = { cedula: "Cédula", passport: "Pasaporte", other: "Otro" };
export const sexLabels: Record<string, string> = { female: "Femenino", male: "Masculino", other: "Otro", unknown: "Desconocido" };
export const bloodTypes = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
type Section = "personal" | "clinical-basic" | "clinical-contacts";
type Props = { value: PatientDemographics; onChange: (value: PatientDemographics) => void; section: Section };
type Locality = { id: number; name: string };

function SectionTitle({ icon, children }: { icon: PatientFormIconName; children: string }) {
  return <span className="patient-form-section-title"><PatientFormIcon name={icon} size={22} /><span>{children}</span></span>;
}

function InputWithIcon({ icon, ...props }: ComponentProps<typeof Input> & { icon?: PatientFormIconName }) {
  if (!icon) return <Input {...props} />;
  return <span className="patient-form-input-with-icon"><Input {...props} /><PatientFormIcon name={icon} size={18} /></span>;
}

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
  const input = (key: keyof PatientDemographics, label: string, maxLength = 100, type = "text", className?: string, icon?: PatientFormIconName) =>
    <FormField key={key} label={label} className={className}><InputWithIcon icon={icon} type={type} maxLength={maxLength} value={value[key] ?? ""} onChange={(event) => change(key, event.target.value)} /></FormField>;

  if (section === "clinical-basic") return <FormSection title={<SectionTitle icon="stethoscope">Datos clínicos básicos</SectionTitle>} className="patient-form-basic-clinical-section">
    <FormField label="Sexo registrado (clínico)">
      <Select value={value.registered_sex ?? ""} onChange={(event) => change("registered_sex", event.target.value)}>
        <option value="">Sin registrar</option>
        {Object.entries(sexLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </Select>
    </FormField>
    <FormField label="Tipo sanguíneo">
      <Select value={value.blood_type ?? ""} onChange={(event) => change("blood_type", event.target.value)}>
        <option value="">Desconocido / sin registrar</option>
        {bloodTypes.map((type) => <option key={type}>{type}</option>)}
      </Select>
    </FormField>
  </FormSection>;

  if (section === "clinical-contacts") return <>
    <FormSection title={<SectionTitle icon="phone">Contacto de emergencia</SectionTitle>} className="patient-form-contacts-section">
      {input("emergency_contact_name", "Nombre completo", 150)}
      {input("emergency_contact_relationship", "Parentesco")}
      {input("emergency_contact_mobile", "Teléfono (Celular)", 30, "tel", undefined, "mobile")}
      {input("emergency_contact_home_phone", "Teléfono (Casa)", 30, "tel", "patient-form-contact-home", "home")}
    </FormSection>
    <FormSection title={<SectionTitle icon="users">Tutor / Responsable (opcional)</SectionTitle>} description="Complete si el paciente es menor de edad o requiere un representante." className="patient-form-contacts-section patient-form-guardian-section">
      {input("guardian_name", "Nombre completo", 150)}
      {input("guardian_relationship", "Parentesco")}
      {input("guardian_mobile", "Teléfono (Celular)", 30, "tel", undefined, "mobile")}
      {input("guardian_home_phone", "Teléfono (Casa)", 30, "tel", "patient-form-contact-home", "home")}
    </FormSection>
  </>;

  return <>
    <FormSection title={<SectionTitle icon="pin">Dirección</SectionTitle>} className="patient-form-address-section">
      {input("address", "Dirección", 500, "text", "patient-form-wide")}
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
    <FormSection title={<SectionTitle icon="briefcase">Información adicional</SectionTitle>}>
      {input("nationality", "Nacionalidad")}
      {input("occupation", "Ocupación / Profesión", 150)}
    </FormSection>
  </>;
}
