import { api } from "./api";

export type PrintOriginType = "WEB_DESKTOP" | "WEB_MOBILE" | "WEB_TABLET" | "LOCAL_AGENT" | "SYSTEM";
export type DocumentSecurityClass = "GENERAL" | "ADMINISTRATIVE" | "FINANCIAL" | "CLINICAL" | "SENSITIVE_CLINICAL";
export type AvailableDestination = {
  target_agent: string; target_printer: string; station_name: string; printer_name: string;
  center_id: number; workgroup_id: number; route: "ATLAS_HTTPS";
  lan_channel_available: false; execution_enabled: false; document_authorization_required: true;
};
export type DestinationAvailability = {
  origin_type: PrintOriginType; origin_user: number; source_agent_required: false;
  availability_only: true; execution_enabled: false; destinations: AvailableDestination[];
};
// No token/device cookie and no print submission. Uses the authenticated Atlas API.
export async function listAvailableDestinations(options: {
  origin_type: PrintOriginType; center_id?: number; workgroup_id?: number; paper_name?: string;
}): Promise<DestinationAvailability> {
  const { data } = await api.get<DestinationAvailability>("/local-agents/destinations", { params: options });
  return data;
}
