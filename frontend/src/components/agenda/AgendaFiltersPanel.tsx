import { Button, Card, Select } from "../../ui";
import type { AgendaFilters } from "./agenda";
import { appointmentStatusLabels } from "./agenda";

type Center = { id: number; name: string; city?: string | null };
type Doctor = { id: number; full_name: string; center_ids: number[]; specialties: { id: number; name: string }[] };
export function AgendaFiltersPanel({ filters, centers, doctors, onChange, onClear }: { filters: AgendaFilters; centers: Center[]; doctors: Doctor[]; onChange: (next: AgendaFilters) => void; onClear: () => void }) {
 const visibleDoctors = doctors.filter((doctor) => !filters.centerId || doctor.center_ids.includes(Number(filters.centerId)));
 const specialties = Array.from(new Map(visibleDoctors.flatMap((doctor) => doctor.specialties).map((item) => [item.id, item])).values());
 return <Card className="agenda-filters"><h3 className="atlas-card-title">Filtros</h3><div className="agenda-filter-fields">
  <label className="atlas-label">Centro<Select value={filters.centerId} onChange={(e) => onChange({ ...filters, centerId: e.target.value, doctorId: "" })}><option value="">Todos los centros</option>{centers.map((item) => <option value={item.id} key={item.id}>{item.name}{item.city ? ` · ${item.city}` : ""}</option>)}</Select></label>
  <label className="atlas-label">Médico<Select value={filters.doctorId} onChange={(e) => onChange({ ...filters, doctorId: e.target.value })}><option value="">Todos los médicos</option>{visibleDoctors.map((item) => <option value={item.id} key={item.id}>{item.full_name}</option>)}</Select></label>
  <label className="atlas-label">Especialidad<Select value={filters.specialtyId} onChange={(e) => onChange({ ...filters, specialtyId: e.target.value })}><option value="">Todas las especialidades</option>{specialties.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</Select></label>
  <label className="atlas-label">Estado<Select value={filters.status} onChange={(e) => onChange({ ...filters, status: e.target.value })}><option value="">Todos los estados</option>{Object.entries(appointmentStatusLabels).map(([id, label]) => <option value={id} key={id}>{label}</option>)}</Select></label>
 </div><Button variant="ghost" onClick={onClear}>Limpiar filtros</Button></Card>;
}