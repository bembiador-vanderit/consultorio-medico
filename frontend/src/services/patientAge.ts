type CalendarDate = { year: number; month: number; day: number };
export type PatientAge = { value: number; unit: "days" | "months" | "years" };

export function todayDate(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function calendarDate(value: string): CalendarDate | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  if (year < 1 || date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return { year, month, day };
}

/** Calendar dates, never persisted. Feb 29 birthdays advance on March 1 in non-leap years. */
export function patientAge(dateOfBirth: string, reference: string | Date = todayDate()): number | null {
  const referenceDate = reference instanceof Date ? todayDate(reference) : reference;
  const birth = calendarDate(dateOfBirth), at = calendarDate(referenceDate);
  if (!birth || !at || dateOfBirth > referenceDate) return null;
  return at.year - birth.year - Number(at.month < birth.month || (at.month === birth.month && at.day < birth.day));
}

export function pediatricAge(dateOfBirth: string, reference = todayDate()): PatientAge | null {
  const years = patientAge(dateOfBirth, reference);
  if (years === null) return null;
  if (years >= 2) return { value: years, unit: "years" };
  const birth = calendarDate(dateOfBirth)!, at = calendarDate(reference)!;
  const months = (at.year - birth.year) * 12 + at.month - birth.month - Number(at.day < birth.day);
  if (months >= 1) return { value: months, unit: "months" };
  const utc = (value: string) => new Date(`${value}T00:00:00Z`).getTime();
  return { value: Math.round((utc(reference) - utc(dateOfBirth)) / 86400000), unit: "days" };
}

export function patientAgeLabel(dateOfBirth: string, reference = todayDate()): string {
  const age = pediatricAge(dateOfBirth, reference);
  if (!age) return "Edad no disponible";
  const units = { days: ["día", "días"], months: ["mes", "meses"], years: ["año", "años"] };
  return `${age.value} ${units[age.unit][age.value === 1 ? 0 : 1]}`;
}
