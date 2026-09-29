/** Presentation metadata only: never clinical records, permissions or workflow state. */
export type WorkspaceId = "dashboard" | "agenda" | "consultation";
export type LayoutSource = "atlas" | "organization" | "center-role" | "user";
export type WorkspaceModuleLayout = {
  moduleId: string;
  zone: string;
  order: number;
  visible: boolean;
};
export type WorkspaceLayout = {
  workspaceId: WorkspaceId;
  layoutVersion: 1;
  source: LayoutSource;
  roleContext?: string;
  modules: readonly WorkspaceModuleLayout[];
};
/** Future precedence, from baseline to most specific. No persistence or merge engine yet. */
export const layoutPrecedence: readonly LayoutSource[] = ["atlas", "organization", "center-role", "user"];
