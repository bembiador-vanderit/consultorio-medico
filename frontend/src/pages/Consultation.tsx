import ConsultationWorkspace from "../components/consultation/ConsultationWorkspace";
import type { NavigationGuardRegistrar } from "../navigation/navigation";
import type { Appointment } from "../types/appointment";

type Props = { appointment: Appointment; onBack: () => void; registerNavigationGuard?: NavigationGuardRegistrar };

/** Page adapter: the episode-scoped workspace owns the consultation screen. */
export default function Consultation({ appointment, onBack, registerNavigationGuard }: Props) {
  return <ConsultationWorkspace appointment={appointment} onBack={onBack} registerNavigationGuard={registerNavigationGuard} />;
}
