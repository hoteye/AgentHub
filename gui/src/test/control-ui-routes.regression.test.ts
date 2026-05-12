import { describe, expect, it } from "vitest";

import {
  GUI_ROUTES,
  pathForRoute,
  routeFromPath,
  routesForGroup,
} from "../routes.ts";

describe("control ui routes regression", () => {
  it("keeps sessions route wired to control group", () => {
    const sessions = GUI_ROUTES.find((item) => item.id === "sessions");
    expect(sessions).toBeDefined();
    expect(sessions?.path).toBe("/sessions");
    expect(sessions?.group).toBe("control");
  });

  it("keeps channels route wired to control group", () => {
    const channels = GUI_ROUTES.find((item) => item.id === "channels");
    expect(channels).toBeDefined();
    expect(channels?.path).toBe("/channels");
    expect(channels?.group).toBe("control");
  });

  it("keeps logs route wired to settings group", () => {
    const logs = GUI_ROUTES.find((item) => item.id === "logs");
    expect(logs).toBeDefined();
    expect(logs?.path).toBe("/logs");
    expect(logs?.group).toBe("settings");
  });

  it("keeps codex route wired to agent group", () => {
    const codex = GUI_ROUTES.find((item) => item.id === "codex");
    expect(codex).toBeDefined();
    expect(codex?.path).toBe("/codex");
    expect(codex?.group).toBe("agent");
  });

  it("keeps config and debug routes wired to settings group", () => {
    const config = GUI_ROUTES.find((item) => item.id === "config");
    const debug = GUI_ROUTES.find((item) => item.id === "debug");
    expect(config?.path).toBe("/config");
    expect(config?.group).toBe("settings");
    expect(debug?.path).toBe("/debug");
    expect(debug?.group).toBe("settings");
  });

  it("keeps nodes route wired to control group", () => {
    const nodes = GUI_ROUTES.find((item) => item.id === "nodes");
    expect(nodes).toBeDefined();
    expect(nodes?.path).toBe("/nodes");
    expect(nodes?.group).toBe("control");
  });

  it("resolves sessions route path", () => {
    expect(pathForRoute("sessions")).toBe("/sessions");
    expect(routeFromPath("/sessions")).toBe("sessions");
  });

  it("resolves logs route path", () => {
    expect(pathForRoute("logs")).toBe("/logs");
    expect(routeFromPath("/logs")).toBe("logs");
  });

  it("keeps chat/control/settings route groups non-empty", () => {
    expect(routesForGroup("chat").length).toBeGreaterThan(0);
    expect(routesForGroup("control").length).toBeGreaterThan(0);
    expect(routesForGroup("agent").length).toBeGreaterThan(0);
    expect(routesForGroup("settings").length).toBeGreaterThan(0);
  });
});
