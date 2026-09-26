import type { ClinicalAddendum, ClinicalHistory, Diagnosis, Prescription, RequestedTest, VitalSigns } from "./clinical";
import type { LaboratoryOrder, StudyOrder } from "./clinicalOrder";

export type HistoricalConsultationDetails = {
  diagnoses: Diagnosis[];
  prescriptions: Prescription[];
  requestedTests: RequestedTest[];
  vitalSigns: VitalSigns | null;
  addenda: ClinicalAddendum[];
  laboratoryOrders: LaboratoryOrder[];
  studyOrders: StudyOrder[];
};

export type HistoricalConsultation = {
  history: ClinicalHistory;
  details: HistoricalConsultationDetails;
};
