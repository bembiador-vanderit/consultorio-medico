import type { AxiosRequestConfig } from "axios";

import { clinicalApi } from "./clinicalApi";
import type { HistoricalConsultationDetails } from "../types/historicalConsultation";

export type HistoricalReadOptions = Pick<AxiosRequestConfig, "signal">;

/** Loads the immutable resources for one history without consulting live catalogs. */
export function loadHistoricalConsultationDetails(historyId: number, options?: HistoricalReadOptions): Promise<HistoricalConsultationDetails> {
  return Promise.all([
    clinicalApi.getDiagnoses(historyId, options),
    clinicalApi.getPrescriptions(historyId, options),
    clinicalApi.getRequestedTests(historyId, options),
    clinicalApi.getVitalSigns(historyId, options),
    clinicalApi.getAddenda(historyId, options),
    clinicalApi.getLaboratoryOrders(historyId, options),
    clinicalApi.getStudyOrders(historyId, options),
  ]).then(([diagnoses, prescriptions, requestedTests, vitalSigns, addenda, laboratoryOrders, studyOrders]) => ({
    diagnoses,
    prescriptions,
    requestedTests,
    vitalSigns,
    addenda,
    laboratoryOrders,
    studyOrders,
  }));
}
