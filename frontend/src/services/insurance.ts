export function insuranceError(error: any): string {
  const detail = error?.response?.data?.detail;
  return Array.isArray(detail) ? detail.map((item: any) => item.msg).join(". ") : typeof detail === "string" ? detail : "No fue posible completar la operación. Intente de nuevo.";
}
