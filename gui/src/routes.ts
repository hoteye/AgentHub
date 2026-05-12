export const GUI_ROUTE_GROUPS = [
  {
    id: "chat",
    label: "Chat",
    description: "对话、任务与总览",
  },
  {
    id: "control",
    label: "Control",
    description: "控制面与运行态",
  },
  {
    id: "agent",
    label: "Agent",
    description: "Agent 与工具面（规划中）",
  },
  {
    id: "settings",
    label: "Settings",
    description: "配置与运维",
  },
] as const;

export const GUI_ROUTES = [
  { id: "workbench", label: "工作台", path: "/", group: "chat" },
  { id: "chat", label: "对话与任务", path: "/chat", group: "chat" },
  { id: "codex", label: "Codex UI", path: "/codex", group: "agent" },
  { id: "browser", label: "浏览器控制", path: "/browser", group: "control" },
  { id: "channels", label: "Channels", path: "/channels", group: "control" },
  { id: "nodes", label: "Nodes / Devices", path: "/nodes", group: "control" },
  { id: "approvals", label: "审批与审计", path: "/approvals", group: "control" },
  { id: "sessions", label: "Sessions / Runs", path: "/sessions", group: "control" },
  { id: "plugins", label: "插件与连接器", path: "/plugins", group: "control" },
  { id: "auth", label: "Auth / Scope", path: "/auth", group: "settings" },
  { id: "config", label: "Config", path: "/config", group: "settings" },
  { id: "debug", label: "Debug", path: "/debug", group: "settings" },
  { id: "logs", label: "Logs", path: "/logs", group: "settings" },
  { id: "settings", label: "设置", path: "/settings", group: "settings" },
] as const;

export type GuiRouteId = (typeof GUI_ROUTES)[number]["id"];
export type GuiRouteGroupId = (typeof GUI_ROUTE_GROUPS)[number]["id"];
export type GuiRoute = (typeof GUI_ROUTES)[number];

const PATH_TO_ROUTE = new Map<string, GuiRouteId>(
  GUI_ROUTES.map((route) => [route.path.toLowerCase(), route.id]),
);

const GROUP_TO_ROUTES = new Map<GuiRouteGroupId, readonly GuiRoute[]>(
  GUI_ROUTE_GROUPS.map((group) => [
    group.id,
    GUI_ROUTES.filter((route) => route.group === group.id),
  ]),
);

export function normalizePath(pathname: string): string {
  const raw = pathname.trim() || "/";
  const prefixed = raw.startsWith("/") ? raw : `/${raw}`;
  if (prefixed.length > 1 && prefixed.endsWith("/")) {
    return prefixed.slice(0, -1);
  }
  return prefixed;
}

export function pathForRoute(route: GuiRouteId): string {
  const match = GUI_ROUTES.find((entry) => entry.id === route);
  return match?.path ?? "/";
}

export function routesForGroup(group: GuiRouteGroupId): readonly GuiRoute[] {
  return GROUP_TO_ROUTES.get(group) ?? [];
}

export function routeFromPath(pathname: string): GuiRouteId {
  const normalized = normalizePath(pathname).toLowerCase();
  return PATH_TO_ROUTE.get(normalized) ?? "workbench";
}
