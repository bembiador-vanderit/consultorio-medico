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
type Country = { code: string; name: string };
type Level = { id: number; position: number; key: string; display_label: string };
type Unit = { id: number; name: string; parent_id: number | null };
type TerritorialPathItem = NonNullable<PatientDemographics["territorial_path"]>[number];

function SectionTitle({ icon, children }: { icon: PatientFormIconName; children: string }) {
  return <span className="patient-form-section-title"><PatientFormIcon name={icon} size={22} /><span>{children}</span></span>;
}

function InputWithIcon({ icon, ...props }: ComponentProps<typeof Input> & { icon?: PatientFormIconName }) {
  return icon ? <span className="patient-form-input-with-icon"><Input {...props} /><PatientFormIcon name={icon} size={18} /></span> : <Input {...props} />;
}

export default function PatientDemographicFields({ value, onChange, section }: Props) {
  const [countries, setCountries] = useState<Country[]>([]);
  const [levels, setLevels] = useState<Level[]>([]);
  const [roots, setRoots] = useState<Unit[]>([]);
  const [children, setChildren] = useState<Unit[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const path = value.territorial_path ?? [];
  const levelOne = levels[0];
  const levelTwo = levels[1];
  const rootId = path.find((item) => item.level === levelOne?.position)?.unit_id ?? (value.territorial_unit_id && !levelTwo ? value.territorial_unit_id : null);
  const childId = path.find((item) => item.level === levelTwo?.position)?.unit_id ?? (levelTwo ? value.territorial_unit_id : null);

  useEffect(() => {
    if (section !== "personal") return;
    let active = true;
    Promise.all([api.get<Country[]>("/regional/countries"), api.get<{ default_country_code: string }>("/regional/settings")])
      .then(([countryResponse, settingsResponse]) => {
        if (!active) return;
        setCountries(countryResponse.data);
        // Legacy values must remain untouched until a person explicitly maps them.
        if (!value.country_code && !value.province && !value.locality_id) {
          onChange({ ...value, country_code: settingsResponse.data.default_country_code });
        }
      })
      .catch(() => active && setCatalogError("No fue posible cargar el catálogo territorial. Los datos existentes se conservarán."));
    return () => { active = false; };
  }, [section]);

  useEffect(() => {
    if (section !== "personal" || !value.country_code) {
      setLevels([]);
      return;
    }
    let active = true;
    api.get<Level[]>(`/regional/countries/${value.country_code}/levels`)
      .then(({ data }) => active && setLevels(data))
      .catch(() => active && setCatalogError("No fue posible cargar los niveles territoriales."));
    return () => { active = false; };
  }, [section, value.country_code]);

  useEffect(() => {
    if (!levelOne || !value.country_code) {
      setRoots([]);
      return;
    }
    let active = true;
    api.get<Unit[]>("/regional/territories", { params: { country_code: value.country_code, level: levelOne.id } })
      .then(({ data }) => active && setRoots(data))
      .catch(() => active && setCatalogError("No fue posible cargar los territorios."));
    return () => { active = false; };
  }, [value.country_code, levelOne?.id]);

  useEffect(() => {
    if (!levelTwo || !rootId || !value.country_code) {
      setChildren([]);
      return;
    }
    let active = true;
    api.get<Unit[]>("/regional/territories", { params: { country_code: value.country_code, level: levelTwo.id, parent_id: rootId } })
      .then(({ data }) => active && setChildren(data))
      .catch(() => active && setCatalogError("No fue posible cargar los territorios."));
    return () => { active = false; };
  }, [value.country_code, levelTwo?.id, rootId]);

  const change = (key: keyof PatientDemographics, next: string) => onChange({ ...value, [key]: next || null });
  const input = (key: keyof PatientDemographics, label: string, maxLength = 100, type = "text", className?: string, icon?: PatientFormIconName) =>
    <FormField key={key} label={label} className={className}>
      <InputWithIcon icon={icon} type={type} maxLength={maxLength} value={(value[key] as string | null | undefined) ?? ""} onChange={(event) => change(key, event.target.value)} />
    </FormField>;

  function selectCountry(countryCode: string) {
    onChange({ ...value, country_code: countryCode || null, territorial_unit_id: null, territorial_path: [], sector_locality: value.sector_locality ?? null });
  }

  function selectRoot(rawId: string) {
    if (!levelOne) return;
    const unitId = rawId ? Number(rawId) : null;
    const root = roots.find((item) => item.id === unitId);
    const rootPath: TerritorialPathItem[] = root ? [{ level: levelOne.position, key: levelOne.key, label: levelOne.display_label, unit_id: root.id, name: root.name }] : [];
    onChange({ ...value, territorial_unit_id: levelTwo ? null : unitId, territorial_path: rootPath });
  }

  function selectChild(rawId: string) {
    if (!levelTwo) return;
    const unitId = rawId ? Number(rawId) : null;
    const child = children.find((item) => item.id === unitId);
    const withoutChild = path.filter((item) => item.level !== levelTwo.position);
    const childPath: TerritorialPathItem[] = child ? [...withoutChild, { level: levelTwo.position, key: levelTwo.key, label: levelTwo.display_label, unit_id: child.id, name: child.name }] : withoutChild;
    onChange({ ...value, territorial_unit_id: unitId, territorial_path: childPath });
  }

  if (section === "clinical-basic") return <FormSection title={<SectionTitle icon="stethoscope">Datos clínicos básicos</SectionTitle>}>
    <FormField label="Sexo registrado (clínico)"><Select value={value.registered_sex ?? ""} onChange={(event) => change("registered_sex", event.target.value)}><option value="">Sin registrar</option>{Object.entries(sexLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</Select></FormField>
    <FormField label="Tipo sanguíneo"><Select value={value.blood_type ?? ""} onChange={(event) => change("blood_type", event.target.value)}><option value="">Desconocido / sin registrar</option>{bloodTypes.map((type) => <option key={type}>{type}</option>)}</Select></FormField>
  </FormSection>;

  if (section === "clinical-contacts") return <>
    <FormSection title={<SectionTitle icon="phone">Contacto de emergencia</SectionTitle>} className="patient-form-contacts-section">
      {input("emergency_contact_name", "Nombre completo", 150)}{input("emergency_contact_relationship", "Parentesco")}{input("emergency_contact_mobile", "Teléfono (Celular)", 30, "tel", undefined, "mobile")}{input("emergency_contact_home_phone", "Teléfono (Casa)", 30, "tel", "patient-form-contact-home", "home")}
    </FormSection>
    <FormSection title={<SectionTitle icon="users">Tutor / Responsable (opcional)</SectionTitle>} description="Complete si el paciente es menor de edad o requiere un representante." className="patient-form-contacts-section patient-form-guardian-section">
      {input("guardian_name", "Nombre completo", 150)}{input("guardian_relationship", "Parentesco")}{input("guardian_mobile", "Teléfono (Celular)", 30, "tel", undefined, "mobile")}{input("guardian_home_phone", "Teléfono (Casa)", 30, "tel", "patient-form-contact-home", "home")}
    </FormSection>
  </>;

  return <>
    <FormSection title={<SectionTitle icon="pin">Ubicación / domicilio</SectionTitle>} className="patient-form-address-section">
      <FormField label="País"><Select disabled={Boolean(catalogError)} value={value.country_code ?? ""} onChange={(event) => selectCountry(event.target.value)}><option value="">Seleccione un país</option>{countries.map((country) => <option key={country.code} value={country.code}>{country.name}</option>)}</Select></FormField>
      {levelOne && <FormField label={levelOne.display_label}><Select disabled={Boolean(catalogError)} value={rootId ?? ""} onChange={(event) => selectRoot(event.target.value)}><option value="">Seleccione {levelOne.display_label.toLowerCase()}</option>{roots.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</Select></FormField>}
      {levelTwo && <FormField label={levelTwo.display_label}><Select disabled={Boolean(catalogError) || !rootId} value={childId ?? ""} onChange={(event) => selectChild(event.target.value)}><option value="">Seleccione {levelTwo.display_label.toLowerCase()}</option>{children.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</Select></FormField>}
      {input("sector_locality", "Sector / Localidad", 150)}
      {input("address", "Dirección", 500, "text", "patient-form-wide")}
      {catalogError && <Alert tone="warning" title="Catálogo territorial no disponible">{catalogError}</Alert>}
      {!value.territorial_unit_id && (value.province || value.locality_id) && <p className="atlas-help patient-form-wide">Ubicación anterior: {value.province ?? "Sin provincia"}{value.locality_name ? ` · ${value.locality_name}` : ""}. Puede migrarla manualmente.</p>}
    </FormSection>
    <FormSection title={<SectionTitle icon="briefcase">Información adicional</SectionTitle>}>{input("nationality", "Nacionalidad")}{input("occupation", "Ocupación / Profesión", 150)}</FormSection>
  </>;
}
