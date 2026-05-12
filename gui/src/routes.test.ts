import { describe, expect, it } from "vitest";

import { pathForRoute, routeFromPath } from "./routes.ts";

describe("routes", () => {
  it("maps root to workbench", () => {
    expect(routeFromPath("/")).toBe("workbench");
  });

  it("normalizes nested route paths", () => {
    expect(routeFromPath("/browser/")).toBe("browser");
    expect(routeFromPath("/channels")).toBe("channels");
    expect(routeFromPath("/codex")).toBe("codex");
    expect(routeFromPath("/nodes")).toBe("nodes");
    expect(routeFromPath("settings")).toBe("settings");
  });

  it("returns canonical paths", () => {
    expect(pathForRoute("plugins")).toBe("/plugins");
    expect(pathForRoute("codex")).toBe("/codex");
    expect(pathForRoute("workbench")).toBe("/");
  });
});
