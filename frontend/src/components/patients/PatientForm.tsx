import { FormEvent, useEffect, useId, useState } from "react";
import { Alert, Button, FormField, FormSection, Input, Modal, Radio, Select } from "../../ui";
import "../../pages/patients.css";
import { api } from "../../services/api";
import type { InsuranceCompany, PatientInsurance } from "../../types/insurance";
import { patientAgeLabel, todayDate } from "../../services/patientAge";
import PatientDemographicFields, { documentLabels } from "./PatientDemographicFields";
import type { PatientDemographics, Patient } from "../../types/patient";
import type { User } from "../../types/user";

type PatientIdentity = { id: number; first_name: string; last_name: string; date_of_birth: string; phone_masked: string | null; email_masked: string | null; selection_token: string };

type Props = {
  patient: Patient | null;
  onClose: () => void;
  onSaved: (patient: Patient) => void;
  onExistingSelected: (patient: Patient) => void;
  user: User;
};

export default function PatientForm({ patient, onClose, onSaved, onExistingSelected, user }: Props) {
  const [demographics, setDemographics] = useState<PatientDemographics>(() => Object.fromEntries(["document_type", "document_number", "home_phone", "registered_sex", "blood_type", "address", "province", "nationality", "occupation", "emergency_contact_name", "emergency_contact_relationship", "emergency_contact_mobile", "emergency_contact_home_phone", "guardian_name", "guardian_relationship", "guardian_mobile", "guardian_home_phone", "locality_id"].map((key) => [key, patient?.[key as keyof PatientDemographics] ?? null])));
  const [firstName, setFirstName] = useState(patient?.first_name || "");
  const [lastName, setLastName] = useState(patient?.last_name || "");
  const [dateOfBirth, setDateOfBirth] = useState(patient?.date_of_birth || "");
  const [phone, setPhone] = useState(patient?.phone || "");
  const [email, setEmail] = useState(patient?.email || "");
  const [hasInsurance, setHasInsurance] = useState(false);
  const [companies, setCompanies] = useState<InsuranceCompany[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [memberNumber, setMemberNumber] = useState("");
  const [planName, setPlanName] = useState("");
  const [currentInsurance, setCurrentInsurance] = useState<PatientInsurance | null>(null);
  const [loadingInsurance, setLoadingInsurance] = useState(Boolean(patient));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [identityMatches, setIdentityMatches] = useState<PatientIdentity[]>([]);
  const formId = useId();
  const insuranceGroupId = useId();
  const [insuranceDirty, setInsuranceDirty] = useState(false);
  const [insuranceReady, setInsuranceReady] = useState(false);
  const [insuranceError, setInsuranceError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadInsurance() {
      setLoadingInsurance(Boolean(patient));
      try {
        const { data: insuranceCompanies } = await api.get<InsuranceCompany[]>("/insurance/companies");
        if (cancelled) return;
        setCompanies(insuranceCompanies);
        if (insuranceCompanies.length > 0 && !companyId) {
          setCompanyId(String(insuranceCompanies[0].id));
        }

        if (!patient) { setInsuranceReady(true); return; }
        const { data: patientInsurances } = await api.get<PatientInsurance[]>(`/insurance/patients/${patient.id}`);
        if (cancelled) return;
        const active = patientInsurances.find((item) => item.is_active && item.is_primary) ?? patientInsurances.find((item) => item.is_active) ?? null;
        setCurrentInsurance(active);
        setInsuranceReady(true);
        if (active) {
          setHasInsurance(true);
          setCompanyId(String(active.insurance_company_id));
          setMemberNumber(active.member_number);
          setPlanName(active.plan_name || "");
        }
      } catch (err: any) {
        if (!cancelled) setInsuranceError(err?.response?.data?.detail || "No fue posible cargar el seguro. Los datos de seguro se conservarán al editar.");
      } finally {
        if (!cancelled) setLoadingInsurance(false);
      }
    }

    void loadInsurance();
    return () => { cancelled = true; };
  }, [patient?.id]);

  function selectInsurance(value: boolean) {
    setInsuranceDirty(true);
    setHasInsurance(value);
    if (!value) {
      setMemberNumber("");
      setPlanName("");
      setCurrentInsurance(null);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");

    if (hasInsurance && (!companyId || !memberNumber.trim())) {
      setError("Para registrar un seguro debe seleccionar la ARS e indicar el número de afiliado.");
      setSaving(false);
      return;
    }

    const insuranceChanged = hasInsurance && (
      !currentInsurance ||
      currentInsurance.insurance_company_id !== Number(companyId) ||
      currentInsurance.member_number !== memberNumber.trim() ||
      (currentInsurance.plan_name || "") !== planName.trim()
    );

    const payload = {
      ...demographics,
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      date_of_birth: dateOfBirth,
      phone: phone.trim() || null,
      email: email.trim() || null,
      ...(!patient || insuranceDirty || (insuranceReady && insuranceChanged) ? { has_insurance: hasInsurance,
      insurance: insuranceChanged ? {
        insurance_company_id: Number(companyId),
        member_number: memberNumber.trim(),
        plan_name: planName.trim() || null,
        is_primary: true,
      } : null } : {}),
    };

    try {
      if (!patient && dateOfBirth && (phone.trim() || email.trim()) && (user.roles.includes("doctor") || user.roles.includes("admin"))) {
        const identifier = email.trim() || phone.trim();
        const { data } = await api.get<PatientIdentity[]>("/patients/identity-search", { params: {
          date_of_birth: dateOfBirth,
          phone: identifier.includes("@") ? undefined : identifier,
          email: identifier.includes("@") ? identifier : undefined,
        } });
        if (data.length) {
          setIdentityMatches(data);
          setError("Ya existe una identidad coincidente. Seleccione el registro existente para evitar duplicarlo.");
          return;
        }
      }
      const response = patient
        ? await api.put<Patient>(`/patients/${patient.id}`, payload)
        : await api.post<Patient>("/patients", payload);
      onSaved(response.data);
    } catch (err: any) {
      // Do not log request payloads containing patient identifiers.
      const detail = err?.response?.data?.detail;
      setError(
        Array.isArray(detail)
          ? detail.map((item: any) => item.msg).join(", ")
          : detail || "No fue posible guardar el paciente."
      );
    } finally {
      setSaving(false);
    }
  }

  return <Modal title={patient ? "Editar paciente" : "Nuevo paciente"} description="Complete los datos del paciente y su cobertura médica." open onClose={() => { if (!saving) onClose(); }} closeLabel="Cerrar formulario de paciente" footer={<div className="patient-form-actions"><Button variant="outline" disabled={saving} onClick={onClose}>Cancelar</Button><Button type="submit" form={formId} loading={saving} loadingLabel="Guardando..." disabled={loadingInsurance}>{patient ? "Guardar cambios" : "Guardar paciente"}</Button></div>}>
    <form id={formId} onSubmit={save} className="patient-form">
      {error && <Alert tone="danger" title="Revise los datos del paciente">{error}</Alert>}
      {identityMatches.length > 0 && <div className="patient-identity-matches">{identityMatches.map((match) => <Button key={match.id} variant="outline" onClick={() => onExistingSelected({ id: match.id, first_name: match.first_name, last_name: match.last_name, date_of_birth: match.date_of_birth, phone: match.phone_masked, email: null, created_at: new Date().toISOString(), selection_token: match.selection_token })}><strong>Usar {match.first_name} {match.last_name}</strong><span className="atlas-help"> · {match.date_of_birth}{match.phone_masked ? ` · ${match.phone_masked}` : ""}</span></Button>)}</div>}
      {!patient && user.roles.includes("secretary") && <Alert title="Seleccionar un paciente existente">Para buscar un paciente existente, use Nueva cita y seleccione primero el centro y el médico autorizado.</Alert>}
      <div className="patient-form-columns">
        <section className="patient-form-folder patient-form-folder--personal" aria-labelledby={`${formId}-personal-title`}>
          <header className="patient-form-folder-heading patient-form-folder-heading--personal">
            <span className="patient-form-folder-number" aria-hidden="true">1</span>
            <span><strong id={`${formId}-personal-title`}>Datos personales</strong><small>Información básica y de contacto</small></span>
          </header>
          <div className="patient-form-folder-content">
            <FormSection title="Identificación">
              <FormField label="Nombre" required><Input minLength={2} maxLength={100} autoComplete="given-name" value={firstName} onChange={(e) => setFirstName(e.target.value)} /></FormField>
              <FormField label="Apellido" required><Input minLength={2} maxLength={100} autoComplete="family-name" value={lastName} onChange={(e) => setLastName(e.target.value)} /></FormField>
              <FormField label="Tipo de documento">
                <Select value={demographics.document_type ?? ""} onChange={(event) => setDemographics({ ...demographics, document_type: event.target.value || null, ...(!event.target.value ? { document_number: null } : {}) })}>
                  <option value="">Sin documento</option>
                  {Object.entries(documentLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </Select>
              </FormField>
              <FormField label="Número de documento"><Input maxLength={100} value={demographics.document_number ?? ""} onChange={(event) => setDemographics({ ...demographics, document_number: event.target.value || null })} /></FormField>
              <FormField label="Fecha de nacimiento" required><Input type="date" max={todayDate()} value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} /></FormField>
              <FormField label="Edad calculada"><Input readOnly value={patientAgeLabel(dateOfBirth)} /></FormField>
            </FormSection>
            <FormSection title="Información de contacto">
              <FormField label="Teléfono celular"><Input type="tel" maxLength={30} autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></FormField>
              <FormField label="Teléfono de casa"><Input type="tel" maxLength={30} value={demographics.home_phone ?? ""} onChange={(event) => setDemographics({ ...demographics, home_phone: event.target.value || null })} /></FormField>
              <div className="patient-form-wide"><FormField label="Correo"><Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></FormField></div>
            </FormSection>
            <PatientDemographicFields value={demographics} onChange={setDemographics} section="personal" />
          </div>
        </section>

        <section className="patient-form-folder patient-form-folder--clinical" aria-labelledby={`${formId}-clinical-title`}>
          <header className="patient-form-folder-heading patient-form-folder-heading--clinical">
            <span className="patient-form-folder-number" aria-hidden="true">2</span>
            <span><strong id={`${formId}-clinical-title`}>Datos clínicos</strong><small>Información médica relevante</small></span>
          </header>
          <div className="patient-form-folder-content">
            <PatientDemographicFields value={demographics} onChange={setDemographics} section="clinical-basic" />
            <Alert title="Tipo sanguíneo">El tipo sanguíneo puede ser declarado por el paciente y posteriormente confirmado por laboratorio. El dato registrado aquí no sustituye una confirmación de laboratorio.</Alert>
            <FormSection title="Seguro médico" description="Indique si el paciente tiene seguro médico.">
              {insuranceError && <div className="patient-form-wide"><Alert tone="warning" title="Seguro no disponible">{insuranceError}</Alert></div>}
              {loadingInsurance && <p role="status" className="atlas-help patient-form-wide">Cargando seguro...</p>}
              <div className="patient-form-wide patient-form-actions"><Radio name={insuranceGroupId} label="Sí" checked={hasInsurance} disabled={!insuranceReady || loadingInsurance} onChange={() => selectInsurance(true)} /><Radio name={insuranceGroupId} label="No" checked={!hasInsurance} disabled={!insuranceReady || loadingInsurance} onChange={() => selectInsurance(false)} /></div>
              {hasInsurance && <>
                <FormField label="ARS" required><Select disabled={!insuranceReady || loadingInsurance} value={companyId} onChange={(e) => setCompanyId(e.target.value)}><option value="">Seleccione una ARS</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}{company.code ? ` (${company.code})` : ""}</option>)}</Select></FormField>
                <FormField label="Número de afiliado" required><Input disabled={!insuranceReady || loadingInsurance} maxLength={100} value={memberNumber} onChange={(e) => setMemberNumber(e.target.value)} /></FormField>
                <div className="patient-form-wide"><FormField label="Plan"><Input disabled={!insuranceReady || loadingInsurance} maxLength={150} value={planName} onChange={(e) => setPlanName(e.target.value)} /></FormField></div>
              </>}
              {!hasInsurance && insuranceReady && <p className="atlas-help patient-form-wide">Paciente sin Seguro</p>}
            </FormSection>
            <PatientDemographicFields value={demographics} onChange={setDemographics} section="clinical-contacts" />
          </div>
        </section>
      </div>
    </form>
  </Modal>;
}
