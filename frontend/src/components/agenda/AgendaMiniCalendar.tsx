import { Button } from "../../ui";
import { formatDate, isoDate, parseDate, weekDayLabels } from "./agenda";

export function AgendaMiniCalendar({ selectedDate, onSelect }: { selectedDate: string; onSelect: (value: string) => void }) {
	const selected = parseDate(selectedDate);
	const today = isoDate(new Date());
	const [year, month] = [selected.getFullYear(), selected.getMonth()];
	const first = new Date(year, month, 1);
	const offset = (first.getDay() + 6) % 7;
	const days = new Date(year, month + 1, 0).getDate();
	const cells = Array.from({ length: Math.ceil((offset + days) / 7) * 7 }, (_, index) => index - offset + 1);
	const monthLabel = new Intl.DateTimeFormat("es-DO", { month: "long", year: "numeric" }).format(first);

	return <section className="agenda-calendar" aria-label="Calendario de navegación">
		<div className="agenda-calendar-header">
			<Button size="sm" variant="ghost" aria-label="Mes anterior" onClick={() => onSelect(isoDate(new Date(year, month - 1, 1)))}>‹</Button>
			<strong>{monthLabel}</strong>
			<Button size="sm" variant="ghost" aria-label="Mes siguiente" onClick={() => onSelect(isoDate(new Date(year, month + 1, 1)))}>›</Button>
		</div>
		<div className="agenda-calendar-grid" role="group" aria-label={monthLabel}>
			{weekDayLabels.map((label) => <span className="agenda-calendar-weekday" key={label}>{label}</span>)}
			{cells.map((day, index) => {
				if (day < 1 || day > days) return <span aria-hidden="true" key={`empty-${index}`} />;
				const value = isoDate(new Date(year, month, day));
				const isSelected = selected.getDate() === day;
				const isToday = value === today;
				return <button type="button" key={day}
					className={`agenda-calendar-day${isSelected ? " agenda-calendar-day--selected" : ""}${isToday ? " agenda-calendar-day--today" : ""}`}
					aria-pressed={isSelected} aria-current={isToday ? "date" : undefined}
					aria-label={formatDate(value, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
					onClick={() => onSelect(value)}>{day}</button>;
			})}
		</div>
		<Button variant="outline" size="sm" onClick={() => onSelect(today)}>Hoy</Button>
	</section>;
}