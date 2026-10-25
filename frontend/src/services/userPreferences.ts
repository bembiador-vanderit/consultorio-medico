import { getDefaultGestionOrder, type AccentTheme } from "../navigation/navigation";
import { getDefaultDashboardWidgetOrder } from "../components/dashboard/dashboardModel";
import { api } from "./api";

export type UserPreferences = {
  gestion_menu_order: string[];
  dashboard_widget_order: string[];
  accent_theme: AccentTheme;
};

export function defaultUserPreferences(): UserPreferences {
  return {
    gestion_menu_order: getDefaultGestionOrder(),
    dashboard_widget_order: getDefaultDashboardWidgetOrder(),
    accent_theme: "classic",
  };
}

export async function getUserPreferences(): Promise<UserPreferences> {
  const { data } = await api.get<UserPreferences>("/me/preferences");
  return data;
}

export async function putUserPreferences(preferences: UserPreferences): Promise<UserPreferences> {
  const { data } = await api.put<UserPreferences>("/me/preferences", preferences);
  return data;
}
