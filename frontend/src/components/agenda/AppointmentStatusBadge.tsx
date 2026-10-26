import { StatusBadge } from "../../ui";
import type { Appointment } from "../../types/appointment";
import { appointmentStatusLabels, appointmentStatusTone } from "./agenda";
export function AppointmentStatusBadge({ status }: { status: Appointment["status"] }) { return <StatusBadge className={`appointment-status--${status}`} tone={appointmentStatusTone[status]}>{appointmentStatusLabels[status]}</StatusBadge>; }
