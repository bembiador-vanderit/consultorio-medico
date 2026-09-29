import AppointmentInsurancePanel from "./AppointmentInsurancePanel";
import type { Appointment } from "../../types/appointment";
import type { User } from "../../types/user";
import { Alert, Button, Divider, Modal } from "../../ui";
import { AppointmentStatusBadge } from "./AppointmentStatusBadge";
import { appointmentRules, formatDate, formatTime } from "./agenda";

type Props = {
  appointment: Appointment | null;
  open: boolean;
  onClose: () => void;
  user: User;
  canAccessClinical: boolean;
  onEdit: (appointment: Appointment) => void;
  onAttend: (appointment: Appointment) => void;
  onSetStatus: (
    appointment: Appointment,
    status: Appointment["status"],
  ) => void;
  onDelete: (appointment: Appointment) => void;
  onAddAddendum: (appointment: Appointment) => void;
  busy?: boolean;
  error?: string;
};
export function AppointmentDrawer({
  appointment,
  open,
  onClose,
  user,
  canAccessClinical,
  onEdit,
  onAttend,
  onSetStatus,
  onDelete,
  onAddAddendum,
  busy,
  error,
}: Props) {
  if (!appointment) return null;
  const rules = appointmentRules(appointment, user);
  const active =
    appointment.status === "scheduled" || appointment.status === "confirmed";
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Detalle de cita"
      description="Datos registrados en Atlas."
      closeLabel="Cerrar detalle de cita"
      closeOnBackdrop
      footer={
        <Button variant="outline" disabled={busy} onClick={onClose}>
          Cerrar
        </Button>
      }
    >
      <div className="agenda-drawer">
        <div className="agenda-drawer-title">
          <h3>{appointment.patient_name}</h3>
          <AppointmentStatusBadge status={appointment.status} />
        </div>
        <dl className="agenda-details">
          <div>
            <dt>Fecha</dt>
            <dd>{formatDate(appointment.appointment_date)}</dd>
          </div>
          <div>
            <dt>Hora</dt>
            <dd>{formatTime(appointment.appointment_time)}</dd>
          </div>
          <div>
            <dt>Especialidad</dt>
            <dd>{appointment.specialty_name}</dd>
          </div>
          <div>
            <dt>Centro</dt>
            <dd>{appointment.center_name || "No registrado"}</dd>
          </div>
          <div>
            <dt>Médico responsable</dt>
            <dd>{appointment.doctor_name}</dd>
          </div>
          <div>
            <dt>Motivo</dt>
            <dd>{appointment.reason || "Sin motivo registrado"}</dd>
          </div>
          <div>
            <dt>Observaciones</dt>
            <dd>{appointment.notes || "Sin observaciones"}</dd>
          </div>
        </dl>
        {appointment.coverage_id && (
          <Alert title="Cita bajo cobertura clínica" tone="info">
            {appointment.original_doctor_name
              ? `Médico original: ${appointment.original_doctor_name}.`
              : "La transferencia se registró en Atlas."}
          </Alert>
        )}
        {appointment.has_clinical_history && canAccessClinical && (
          <Alert title="Consulta clínica iniciada" tone="warning">
            El horario y el contexto de la cita están protegidos.
          </Alert>
        )}
        {open && user.permissions?.includes("patients:access") && <AppointmentInsurancePanel key={appointment.id} appointment={appointment} user={user} />}
        <Divider />
        <section aria-labelledby="agenda-actions">
          <h3 id="agenda-actions" className="atlas-card-title">
            Acciones
          </h3>
          {error && (
            <Alert tone="danger" title="No se pudo realizar la acción">
              {error}
            </Alert>
          )}
          <div className="agenda-drawer-actions">
            {!rules.completed && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => onEdit(appointment)}
              >
                Editar cita
              </Button>
            )}
            {active && appointment.status !== "confirmed" && (
              <Button
                variant="secondary"
                loading={busy}
                onClick={() => onSetStatus(appointment, "confirmed")}
              >
                Confirmar
              </Button>
            )}
            {active && !rules.scheduleLocked && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => onEdit(appointment)}
              >
                Reprogramar
              </Button>
            )}
            {rules.canCancel && (
              <Button
                variant="danger"
                loading={busy}
                onClick={() => onSetStatus(appointment, "cancelled")}
              >
                Cancelar
              </Button>
            )}
            {rules.canCancel && (
              <Button
                variant="outline"
                loading={busy}
                onClick={() => onSetStatus(appointment, "no_show")}
              >
                Marcar No asistió
              </Button>
            )}
            {canAccessClinical && rules.canAttend && (
              <Button disabled={busy} onClick={() => onAttend(appointment)}>
                Iniciar consulta
              </Button>
            )}
            {rules.canDelete && (
              <Button
                variant="danger"
                loading={busy}
                onClick={() => onDelete(appointment)}
              >
                Eliminar cita
              </Button>
            )}
            {rules.canAddAddendum && (
              <Button
                disabled={busy}
                onClick={() => onAddAddendum(appointment)}
              >
                Agregar nota adicional
              </Button>
            )}
          </div>
        </section>
      </div>
    </Modal>
  );
}
