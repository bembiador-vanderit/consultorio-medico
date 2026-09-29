import type { ReactNode } from "react";

export type PatientFormIconName = "person-add" | "clinical" | "person" | "phone" | "pin" | "briefcase" | "stethoscope" | "shield" | "users" | "note" | "info" | "calendar" | "mobile" | "home" | "mail" | "save";

const paths: Record<PatientFormIconName, ReactNode> = {
  "person-add": <><circle cx="10" cy="7" r="3.5" /><path d="M3.5 20v-1.5a6.5 6.5 0 0 1 13 0V20" /><path d="M19 8v6m-3-3h6" /></>,
  clinical: <><path d="M3 12h4l2.1-4.5L13 17l2.2-5H21" /><path d="M12 21C7 18 4 15.3 4 10.8A4.3 4.3 0 0 1 12 8a4.3 4.3 0 0 1 8 2.8C20 15.3 17 18 12 21Z" /></>,
  person: <><circle cx="12" cy="7" r="3.5" /><path d="M4 21v-1.5a8 8 0 0 1 16 0V21" /></>,
  phone: <path d="M6.6 3.8 9.3 3l1.8 4.4-1.8 1.4a14.3 14.3 0 0 0 5.9 5.9l1.4-1.8 4.4 1.8-.8 2.7a2.3 2.3 0 0 1-2.5 1.6C10.4 18.1 5.9 13.6 5 6.3a2.3 2.3 0 0 1 1.6-2.5Z" />,
  pin: <><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
  briefcase: <><rect x="3" y="7" width="18" height="12" rx="1.5" /><path d="M8 7V5.5h8V7m-13 5h18m-10 0h2" /></>,
  stethoscope: <><path d="M6 4v5a4 4 0 0 0 8 0V4m-8 0h3m2 0h3M10 13v2a4 4 0 0 0 8 0v-2" /><circle cx="18" cy="12" r="2" /></>,
  shield: <><path d="M12 3 20 6v5c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V6l8-3Z" /><path d="M12 8v6m-3-3h6" /></>,
  users: <><circle cx="9" cy="8" r="3" /><circle cx="17" cy="9" r="2.5" /><path d="M3 20v-1a6 6 0 0 1 12 0v1m1-5a5.5 5.5 0 0 1 5 4v1" /></>,
  note: <><path d="M5 3h14v14l-4 4H5Z" /><path d="M15 21v-4h4M8 8h8m-8 4h8" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5m0-8h.01" /></>,
  calendar: <><rect x="4" y="5" width="16" height="15" rx="1.5" /><path d="M8 3v4m8-4v4M4 10h16" /></>,
  mobile: <><rect x="7" y="3" width="10" height="18" rx="1.5" /><path d="M11 18h2" /></>,
  home: <><path d="m3 11 9-8 9 8v9H4v-9Z" /><path d="M9 20v-6h6v6" /></>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="1.5" /><path d="m4 7 8 6 8-6" /></>,
  save: <><path d="M5 3h12l3 3v15H5Z" /><path d="M8 3v6h8V3m-8 17v-7h8v7" /></>,
};

export function PatientFormIcon({ name, size = 24 }: { name: PatientFormIconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}
