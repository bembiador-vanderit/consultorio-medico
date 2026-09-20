import axios from "axios";
import type { AxiosRequestConfig } from "axios";

import { api } from "./api";
import type {
  ClinicalAddendum,
  ClinicalHistory,
  ClinicalHistoryContent,
  ConsultationContext,
  Diagnosis,
  MedicalStudy,
  Prescription,
  PrescriptionInput,
  RequestedTest,
  VitalSigns,
} from "../types/clinical";
import type { LaboratoryOrder, LaboratoryTest, StudyOrder } from "../types/clinicalOrder";

export type ReadOptions = Pick<AxiosRequestConfig, "signal">;
export type ClinicalHistoryCreate = ClinicalHistoryContent & { appointment_id: number };
export type ClinicalHistoryUpdate = ClinicalHistoryContent & { expected_revision: number };
export type DiagnosisInput = Pick<Diagnosis, "description" | "icd10_code" | "is_primary">;
export type RequestedTestInput = Pick<RequestedTest, "test_name">;
export type VitalSignsInput = Pick<VitalSigns, "systolic_pressure" | "diastolic_pressure" | "heart_rate" | "respiratory_rate" | "temperature_c" | "oxygen_saturation" | "weight_kg" | "height_cm">;
export type LaboratoryOrderInput = { items: Array<{ laboratory_test_id: number }>; notes: string | null };
export type StudyOrderInput = { items: Array<{ medical_study_id: number; region_description: string | null; contrast: "yes" | "no" | "not_applicable"; clinical_notes: string | null }>; notes: string | null };

const studyCatalogCache = new Map<string, Promise<MedicalStudy[]>>();
let laboratoryCatalogRequest: Promise<LaboratoryTest[]> | null = null;

function cached<T>(cache: Map<string, Promise<T>>, key: string, load: () => Promise<T>) {
  const active = cache.get(key);
  if (active) return active;
  const request = load().catch((error: unknown) => {
    cache.delete(key);
    throw error;
  });
  cache.set(key, request);
  return request;
}

function read<T>(url: string, options?: ReadOptions) {
  return api.get<T>(url, options).then((response) => response.data);
}

export function clinicalErrorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError(error) && typeof error.response?.data?.detail === "string") return error.response.data.detail;
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: unknown }).response;
    if (typeof response === "object" && response !== null && "data" in response) {
      const data = (response as { data?: unknown }).data;
      if (typeof data === "object" && data !== null && "detail" in data && typeof (data as { detail?: unknown }).detail === "string") return (data as { detail: string }).detail;
    }
  }
  return fallback;
}

export function isReadAborted(error: unknown) {
  return axios.isCancel(error) || (axios.isAxiosError(error) && error.code === "ERR_CANCELED");
}

export function isRevisionConflict(error: unknown) {
  if (typeof error !== "object" || error === null || !("response" in error)) return false;
  const response = (error as { response?: { status?: unknown; data?: { detail?: unknown } } }).response;
  return response?.status === 409
    && typeof response.data?.detail === "string"
    && response.data.detail.startsWith("La consulta fue modificada en otra sesión o pestaña");
}

export const clinicalApi = {
  getConsultationContext: (appointmentId: number, options?: ReadOptions) => read<ConsultationContext>(`/clinical-history/appointments/${appointmentId}/context`, options),
  getHistory: (historyId: number, options?: ReadOptions) => read<ClinicalHistory>(`/clinical-history/${historyId}`, options),
  createHistory: (patientId: number, payload: ClinicalHistoryCreate) => api.post<ClinicalHistory>(`/clinical-history/patients/${patientId}`, payload).then((response) => response.data),
  updateHistory: (historyId: number, payload: ClinicalHistoryUpdate) => api.put<ClinicalHistory>(`/clinical-history/${historyId}`, payload).then((response) => response.data),
  completeHistory: (historyId: number) => api.post<ClinicalHistory>(`/clinical-history/${historyId}/complete`).then((response) => response.data),

  getVitalSigns: (historyId: number, options?: ReadOptions) => read<VitalSigns | null>(`/clinical-history/${historyId}/vital-signs`, options),
  saveVitalSigns: (historyId: number, payload: VitalSignsInput) => api.put<VitalSigns>(`/clinical-history/${historyId}/vital-signs`, payload).then((response) => response.data),
  getDiagnoses: (historyId: number, options?: ReadOptions) => read<Diagnosis[]>(`/clinical-history/${historyId}/diagnoses`, options),
  createDiagnosis: (historyId: number, payload: DiagnosisInput) => api.post<Diagnosis>(`/clinical-history/${historyId}/diagnoses`, payload).then((response) => response.data),
  deleteDiagnosis: (historyId: number, diagnosisId: number) => api.delete(`/clinical-history/${historyId}/diagnoses/${diagnosisId}`),
  getPrescriptions: (historyId: number, options?: ReadOptions) => read<Prescription[]>(`/clinical-history/${historyId}/prescriptions`, options),
  createPrescription: (historyId: number, payload: PrescriptionInput) => api.post<Prescription>(`/clinical-history/${historyId}/prescriptions`, payload).then((response) => response.data),
  updatePrescription: (historyId: number, prescriptionId: number, payload: PrescriptionInput) => api.put<Prescription>(`/clinical-history/${historyId}/prescriptions/${prescriptionId}`, payload).then((response) => response.data),
  deletePrescription: (historyId: number, prescriptionId: number) => api.delete(`/clinical-history/${historyId}/prescriptions/${prescriptionId}`),
  getRequestedTests: (historyId: number, options?: ReadOptions) => read<RequestedTest[]>(`/clinical-history/${historyId}/requested-tests`, options),
  getAddenda: (historyId: number, options?: ReadOptions) => read<ClinicalAddendum[]>(`/clinical-history/${historyId}/addenda`, options),
  createRequestedTest: (historyId: number, payload: RequestedTestInput) => api.post<RequestedTest>(`/clinical-history/${historyId}/requested-tests`, payload).then((response) => response.data),
  deleteRequestedTest: (requestedTestId: number) => api.delete(`/clinical-history/requested-tests/${requestedTestId}`),

  getStudyCatalog(specialtyId: number | null, includeAll = false) {
    const key = `studies:specialty:${specialtyId ?? "none"}:all:${includeAll}`;
    return cached(studyCatalogCache, key, () => api.get<MedicalStudy[]>("/clinical-catalog/studies", { params: { ...(includeAll ? { include_all: true } : {}), ...(specialtyId ? { specialty_id: specialtyId } : {}) } }).then((response) => response.data));
  },
  getLaboratoryCatalog() {
    if (laboratoryCatalogRequest) return laboratoryCatalogRequest;
    laboratoryCatalogRequest = api.get<LaboratoryTest[]>("/laboratory-tests").then((response) => response.data).catch((error: unknown) => { laboratoryCatalogRequest = null; throw error; });
    return laboratoryCatalogRequest;
  },
  getLaboratoryOrders: (historyId: number, options?: ReadOptions) => read<LaboratoryOrder[]>(`/clinical-history/${historyId}/laboratory-orders`, options),
  getStudyOrders: (historyId: number, options?: ReadOptions) => read<StudyOrder[]>(`/clinical-history/${historyId}/study-orders`, options),
  saveLaboratoryOrder: (historyId: number, payload: LaboratoryOrderInput, additional = false) => api.post(`/clinical-history/${historyId}/laboratory-orders${additional ? "/additional" : ""}`, payload),
  updateLaboratoryOrder: (historyId: number, orderId: number, payload: LaboratoryOrderInput) => api.put(`/clinical-history/${historyId}/laboratory-orders/${orderId}`, payload),
  saveStudyOrder: (historyId: number, payload: StudyOrderInput, additional = false) => api.post(`/clinical-history/${historyId}/study-orders${additional ? "/additional" : ""}`, payload),
  updateStudyOrder: (historyId: number, orderId: number, payload: StudyOrderInput) => api.put(`/clinical-history/${historyId}/study-orders/${orderId}`, payload),
  getPrescriptionPdf: (historyId: number) => api.get<Blob>(`/clinical-history/${historyId}/prescriptions/pdf`, { responseType: "blob" }).then((response) => response.data),
  getRequestedTestsPdf: (historyId: number) => api.get<Blob>(`/clinical-history/${historyId}/requested-tests/pdf`, { responseType: "blob" }).then((response) => response.data),
  getSummaryPdf: (historyId: number) => api.get<Blob>(`/clinical-history/${historyId}/summary/pdf`, { responseType: "blob" }).then((response) => response.data),
  getOrderPdf: (kind: "laboratory" | "study", orderId: number) => api.get<Blob>(`/${kind === "laboratory" ? "laboratory-orders" : "study-orders"}/${orderId}/pdf`, { responseType: "blob" }).then((response) => response.data),
};

export function clearClinicalCatalogCacheForTests() {
  studyCatalogCache.clear();
  laboratoryCatalogRequest = null;
}
