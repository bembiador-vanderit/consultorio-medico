import { useEffect, useRef, useState } from "react";

import { clinicalApi, clinicalErrorMessage, isReadAborted } from "../services/clinicalApi";
import type { ClinicalHistory, ConsultationContext, Diagnosis, MedicalStudy, Prescription, RequestedTest, VitalSigns } from "../types/clinical";

export type ConsultationBootstrap = {
  context: ConsultationContext | null;
  history: ClinicalHistory | null;
  diagnoses: Diagnosis[];
  prescriptions: Prescription[];
  requestedTests: RequestedTest[];
  vitalSigns: VitalSigns | null;
  studyCatalog: MedicalStudy[];
  loading: boolean;
  error: string;
};

const emptyBootstrap: ConsultationBootstrap = {
  context: null,
  history: null,
  diagnoses: [],
  prescriptions: [],
  requestedTests: [],
  vitalSigns: null,
  studyCatalog: [],
  loading: true,
  error: "",
};

/** Keeps episode-scoped clinical data local and publishes only the active request generation. */
export function useConsultationBootstrap(appointmentId: number) {
  const [state, setState] = useState<ConsultationBootstrap>(emptyBootstrap);
  const generationRef = useRef(0);

  useEffect(() => {
    const generation = ++generationRef.current;
    const controller = new AbortController();
    const isCurrent = () => generation === generationRef.current && !controller.signal.aborted;
    setState(emptyBootstrap);

    void (async () => {
      try {
        const context = await clinicalApi.getConsultationContext(appointmentId, { signal: controller.signal });
        if (!isCurrent()) return;
        const history = context.previous_consultations.find((item) => item.appointment_id === context.appointment_id) || null;
        const catalog = clinicalApi.getStudyCatalog(context.specialty_id).catch(() => []);
        if (!history) {
          const studyCatalog = await catalog;
          if (isCurrent()) setState({ ...emptyBootstrap, context, studyCatalog, loading: false });
          return;
        }
        const [studyCatalog, diagnoses, prescriptions, requestedTests, vitalSigns] = await Promise.all([
          catalog,
          clinicalApi.getDiagnoses(history.id, { signal: controller.signal }),
          clinicalApi.getPrescriptions(history.id, { signal: controller.signal }),
          clinicalApi.getRequestedTests(history.id, { signal: controller.signal }),
          clinicalApi.getVitalSigns(history.id, { signal: controller.signal }),
        ]);
        if (isCurrent()) setState({ context, history, diagnoses, prescriptions, requestedTests, vitalSigns, studyCatalog, loading: false, error: "" });
      } catch (error: unknown) {
        if (!isCurrent() || isReadAborted(error)) return;
        setState({ ...emptyBootstrap, loading: false, error: clinicalErrorMessage(error, "No fue posible cargar el contexto de la consulta.") });
      }
    })();

    return () => controller.abort();
  }, [appointmentId]);

  return state;
}
