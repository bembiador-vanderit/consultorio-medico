import { useCallback, useEffect, useRef, useState } from "react";

import { clinicalApi, clinicalErrorMessage, isReadAborted } from "../services/clinicalApi";
import type { ClinicalHistory, ConsultationContext, Diagnosis, Prescription, RequestedTest, VitalSigns } from "../types/clinical";

export type ConsultationBootstrap = {
  context: ConsultationContext | null;
  history: ClinicalHistory | null;
  diagnoses: Diagnosis[];
  prescriptions: Prescription[];
  requestedTests: RequestedTest[];
  vitalSigns: VitalSigns | null;
  loading: boolean;
  refreshing: boolean;
  error: string;
  version: number;
};

const emptyBootstrap: ConsultationBootstrap = {
  context: null,
  history: null,
  diagnoses: [],
  prescriptions: [],
  requestedTests: [],
  vitalSigns: null,
  loading: true,
  refreshing: false,
  error: "",
  version: 0,
};

/** Keeps episode-scoped clinical data local and publishes only the active request generation. */
export function useConsultationBootstrap(appointmentId: number) {
  const [state, setState] = useState<ConsultationBootstrap>(emptyBootstrap);
  const generationRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    const generation = ++generationRef.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const isCurrent = () => generation === generationRef.current && !controller.signal.aborted;
    setState((current) => ({ ...current, loading: current.context === null, refreshing: current.context !== null, error: "" }));

    try {
      const context = await clinicalApi.getConsultationContext(appointmentId, { signal: controller.signal });
      if (!isCurrent()) return false;
      const history = context.previous_consultations.find((item) => item.appointment_id === context.appointment_id) || null;
      if (!history) {
        setState((current) => ({ ...emptyBootstrap, context, loading: false, refreshing: false, version: current.version + 1 }));
        return true;
      }
      const [diagnoses, prescriptions, requestedTests, vitalSigns] = await Promise.all([
        clinicalApi.getDiagnoses(history.id, { signal: controller.signal }),
        clinicalApi.getPrescriptions(history.id, { signal: controller.signal }),
        clinicalApi.getRequestedTests(history.id, { signal: controller.signal }),
        clinicalApi.getVitalSigns(history.id, { signal: controller.signal }),
      ]);
      if (!isCurrent()) return false;
      setState((current) => ({ context, history, diagnoses, prescriptions, requestedTests, vitalSigns, loading: false, refreshing: false, error: "", version: current.version + 1 }));
      return true;
    } catch (error: unknown) {
      if (!isCurrent() || isReadAborted(error)) return false;
      setState((current) => ({ ...current, loading: false, refreshing: false, error: clinicalErrorMessage(error, "No fue posible cargar el contexto de la consulta.") }));
      return false;
    } finally {
      if (isCurrent()) controllerRef.current = null;
    }
  }, [appointmentId]);

  useEffect(() => {
    setState(emptyBootstrap);
    void load();
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [load]);

  return { ...state, reload: load };
}
