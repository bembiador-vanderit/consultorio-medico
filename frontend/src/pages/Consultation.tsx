import ConsultationWorkspace from "../components/consultation/ConsultationWorkspace";
import type { Appointment } from "../types/appointment";

type Props = { appointment: Appointment; onBack: () => void };

/** Page adapter: the episode-scoped workspace owns the consultation screen. */
export default function Consultation({ appointment, onBack }: Props) {
  return <ConsultationWorkspace appointment={appointment} onBack={onBack} />;
}
