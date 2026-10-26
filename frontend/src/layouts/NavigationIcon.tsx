import type { NavigationIcon as IconName } from "../navigation/navigation";

const paths: Record<IconName, string> = {
  home: "m3 10 9-7 9 7v11h-6v-7H9v7H3Z",
  calendar: "M4 5h16v16H4ZM8 3v4m8-4v4M4 10h16m-12 4h2m4 0h2m-8 3h2",
  report: "M5 3h14v18H5Zm4 14v-4m3 4V8m3 9v-6",
  patient: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a8 8 0 0 1 16 0v2",
  bell: "M5 17h14l-2-3V9a5 5 0 0 0-10 0v5Zm5 3h4",
  clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2",
  clinical: "M9 3h6v6h6v6h-6v6H9v-6H3V9h6Z",
  users: "M14 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM2 21v-2a8 8 0 0 1 16 0v2m0-17a4 4 0 0 1 0 8m2 3a7 7 0 0 1 2 6",
  center: "M4 21V7h16v14ZM9 7V3h6v4M9 21v-6h6v6M7 11h2m6 0h2",
};
export function NavigationIcon({ name }: { name: IconName }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name]} /></svg>;
}
