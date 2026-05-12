import { describe, expect, it } from "vitest";

import {
  type MemoryCommandRequest,
  type MemoryCommandResult,
  type MemoryManagementBridge,
  MemoryManagementModel,
} from "./memory-management-page.ts";

class ScriptedMemoryBridge implements MemoryManagementBridge {
  readonly requests: MemoryCommandRequest[] = [];

  constructor(
    private readonly responder: (request: MemoryCommandRequest) => MemoryCommandResult | Promise<MemoryCommandResult>,
  ) {}

  async runMemoryCommand(request: MemoryCommandRequest): Promise<MemoryCommandResult> {
    this.requests.push(request);
    return this.responder(request);
  }
}

describe("memory-management-model", () => {
  it("lists and shows memories with CLI-aligned command semantics", async () => {
    const bridge = new ScriptedMemoryBridge((request) => {
      if (request.action === "list") {
        return {
          ok: true,
          text: [
            "memory_count=2",
            "- mem_project_1 | type=project | status=active | title=Canary first",
            "- mem_project_2 | type=project | status=archived | title=Old rollout",
          ].join("\n"),
        };
      }
      if (request.action === "show") {
        return {
          ok: true,
          text: [
            "memory_id=mem_project_1",
            "scope=project",
            "type=project",
            "status=active",
            "title=Canary first",
            "summary=Deploy with canary before full rollout",
            "tags=release,canary",
            "paths=/repo/service/deploy.py",
            "hit_count=3",
            "last_used_at=2026-04-09T00:00:00Z",
          ].join("\n"),
        };
      }
      return { ok: false, text: "unexpected action", error: "unexpected action" };
    });

    const model = new MemoryManagementModel(bridge, () => "2026-04-09T10:00:00Z", "test.operator");
    model.setFilter({ scope: "project", type: "project", status: "active" });
    await model.listMemories();
    await model.showMemory("mem_project_1");

    const view = model.snapshot();
    expect(bridge.requests[0]?.command).toBe("/memory list --limit 20 --scope project --type project --status active");
    expect(bridge.requests[1]?.command).toBe("/memory show mem_project_1 --scope project");
    expect(view.visibleItems).toHaveLength(1);
    expect(view.visibleItems[0]?.memory_id).toBe("mem_project_1");
    expect(view.selected?.title).toBe("Canary first");
    expect(view.selected?.tags).toEqual(["release", "canary"]);
  });

  it("surfaces blocked_reason and blocks apply when preview is blocked", async () => {
    const bridge = new ScriptedMemoryBridge((request) => {
      if (request.action === "preview") {
        return {
          ok: true,
          text: [
            "memory preview",
            "type=reference",
            "title=Token",
            "summary=Should not save",
            "paths=-",
            "tags=-",
            "reasons=sensitive_pattern",
            "blocked_sensitive=true",
            "blocked_reason=contains_sensitive_content",
          ].join("\n"),
        };
      }
      return { ok: false, text: "unexpected action", error: "unexpected action" };
    });

    const model = new MemoryManagementModel(bridge, () => "2026-04-09T10:01:00Z", "test.operator");
    await model.previewFromLastTurn({ type: "reference" });
    await model.applyPreview();

    const view = model.snapshot();
    expect(bridge.requests).toHaveLength(1);
    expect(view.blockedReason).toBe("contains_sensitive_content");
    expect(view.auditSummary[0]).toMatchObject({
      action: "apply",
      result: "blocked",
      reason: "contains_sensitive_content",
    });
  });

  it("runs save/delete/archive actions and preserves audit summary", async () => {
    const bridge = new ScriptedMemoryBridge((request) => {
      if (request.action === "save") {
        return {
          ok: true,
          text: [
            "memory saved",
            "memory_id=mem_saved_1",
            "scope=project",
            "type=project",
            "status=active",
            "title=Saved memory",
          ].join("\n"),
        };
      }
      if (request.action === "delete") {
        return {
          ok: true,
          text: "memory deleted: mem_saved_1",
        };
      }
      if (request.action === "archive") {
        return {
          ok: false,
          text: "Usage: /memory <list|show|preview|save|delete|debug> [args]",
          error: "archive is not supported by runtime command",
        };
      }
      if (request.action === "list") {
        return {
          ok: true,
          text: "- mem_saved_1 | type=project | status=active | title=Saved memory",
        };
      }
      return { ok: false, text: "unexpected action", error: "unexpected action" };
    });

    const model = new MemoryManagementModel(bridge, () => "2026-04-09T10:02:00Z", "test.operator");
    await model.listMemories();
    await model.saveFromLastTurn({ scope: "project", type: "project" });
    await model.deleteMemory("mem_saved_1");
    await model.archiveMemory("mem_saved_1", "operator_cleanup");

    const view = model.snapshot();
    expect(bridge.requests.map((item) => item.command)).toEqual([
      "/memory list --limit 20",
      "/memory save --from-last-turn --scope project --type project",
      "/memory delete mem_saved_1",
      "/memory archive mem_saved_1 --reason operator_cleanup",
    ]);
    expect(view.allItems[0]?.status).toBe("deleted");
    expect(view.auditSummary[0]).toMatchObject({
      action: "archive",
      result: "error",
    });
    expect(view.blockedReason).toContain("archive");
  });

  it("executes stateful e2e flow across preview/apply/save/list/show/delete/debug", async () => {
    type BridgeMemory = {
      memory_id: string;
      scope: "project";
      memory_type: "project";
      status: "active" | "deleted";
      title: string;
      summary: string;
      tags: string[];
      paths: string[];
      hit_count: number;
      last_used_at: string;
    };

    const store = new Map<string, BridgeMemory>();
    let sequence = 0;
    const bridge = new ScriptedMemoryBridge((request) => {
      if (request.action === "preview") {
        return {
          ok: true,
          text: [
            "memory preview",
            "type=project",
            "title=Canary guardrail",
            "summary=Keep canary-first rollout with smoke checks",
            "paths=/repo/service/deploy.py,/repo/service/smoke_test.py",
            "tags=release,canary",
            "reasons=from_last_turn,non_derivable_candidate",
            "blocked_sensitive=false",
            "blocked_reason=-",
          ].join("\n"),
        };
      }
      if (request.action === "apply" || request.action === "save") {
        sequence += 1;
        const memoryId = `mem_e2e_${sequence}`;
        const item: BridgeMemory = {
          memory_id: memoryId,
          scope: "project",
          memory_type: "project",
          status: "active",
          title: sequence === 1 ? "Canary guardrail" : "Smoke-check gate",
          summary: "Keep canary-first rollout with smoke checks",
          tags: ["release", "canary"],
          paths: ["/repo/service/deploy.py", "/repo/service/smoke_test.py"],
          hit_count: 1,
          last_used_at: "2026-04-09T10:30:00Z",
        };
        store.set(memoryId, item);
        return {
          ok: true,
          text: [
            "memory saved",
            `memory_id=${item.memory_id}`,
            `scope=${item.scope}`,
            `type=${item.memory_type}`,
            `status=${item.status}`,
            `title=${item.title}`,
            `summary=${item.summary}`,
            `tags=${item.tags.join(",")}`,
            `paths=${item.paths.join(",")}`,
            `hit_count=${item.hit_count}`,
            `last_used_at=${item.last_used_at}`,
          ].join("\n"),
        };
      }
      if (request.action === "list") {
        const active = Array.from(store.values()).filter((item) => item.status === "active");
        return {
          ok: true,
          text: [
            `memory_count=${active.length}`,
            ...active.map((item) => `- ${item.memory_id} | type=${item.memory_type} | status=${item.status} | title=${item.title}`),
          ].join("\n"),
        };
      }
      if (request.action === "show") {
        const memoryId = String(request.params.memory_id || "").trim();
        const item = store.get(memoryId);
        if (!item) {
          return { ok: false, text: `memory not found: ${memoryId}`, error: `memory not found: ${memoryId}` };
        }
        return {
          ok: true,
          text: [
            `memory_id=${item.memory_id}`,
            `scope=${item.scope}`,
            `type=${item.memory_type}`,
            `status=${item.status}`,
            `title=${item.title}`,
            `summary=${item.summary}`,
            `tags=${item.tags.join(",")}`,
            `paths=${item.paths.join(",")}`,
            `hit_count=${item.hit_count}`,
            `last_used_at=${item.last_used_at}`,
          ].join("\n"),
        };
      }
      if (request.action === "delete") {
        const memoryId = String(request.params.memory_id || "").trim();
        const item = store.get(memoryId);
        if (!item) {
          return { ok: false, text: `memory delete failed: ${memoryId}`, error: `memory delete failed: ${memoryId}` };
        }
        store.set(memoryId, { ...item, status: "deleted" });
        return { ok: true, text: `memory deleted: ${memoryId}` };
      }
      if (request.action === "debug") {
        const active = Array.from(store.values()).filter((item) => item.status === "active");
        if (active.length === 0) {
          return {
            ok: true,
            text: [
              "recalled_memory_count=0",
              "snapshot_recalled_count=0",
              "snapshot_recalled_ids=-",
              "snapshot_blocked_reason=no_active_memories",
              "snapshot_query_paths=-",
              "snapshot_recalled_types=-",
              "snapshot_ranking_explainability_count=0",
            ].join("\n"),
          };
        }
        const top = active[0];
        return {
          ok: true,
          text: [
            "recalled_memory_count=1",
            "snapshot_recalled_count=1",
            `snapshot_recalled_ids=${top.memory_id}`,
            "snapshot_blocked_reason=-",
            "snapshot_query_paths=service/deploy.py",
            "snapshot_recalled_types=project",
            "snapshot_ranking_explainability_count=1",
            `# rank=1 | memory_id=${top.memory_id} | type=project | score=6.2 | selected=true | reasons=path_overlap,tag_overlap`,
          ].join("\n"),
        };
      }
      return { ok: false, text: "unexpected action", error: "unexpected action" };
    });

    const model = new MemoryManagementModel(bridge, () => "2026-04-09T10:30:00Z", "test.operator");
    model.setFilter({ scope: "project", type: "project", status: "active", limit: 20 });

    await model.previewFromLastTurn({ type: "project" });
    await model.applyPreview();
    await model.saveFromLastTurn({ scope: "project", type: "project" });
    await model.listMemories();

    let view = model.snapshot();
    expect(view.allItems).toHaveLength(2);
    const ids = view.allItems.map((item) => item.memory_id);
    expect(ids).toEqual(["mem_e2e_1", "mem_e2e_2"]);

    await model.showMemory(ids[0]);
    await model.refreshDebug(5);
    view = model.snapshot();
    expect(view.selected?.memory_id).toBe("mem_e2e_1");
    expect(view.blockedReason).toBe("");
    expect(view.explainability[0]).toMatchObject({
      rank: 1,
      memory_id: "mem_e2e_1",
      memory_type: "project",
      score: 6.2,
      selected: true,
    });

    await model.deleteMemory(ids[0]);
    await model.deleteMemory(ids[1]);
    await model.listMemories();
    await model.refreshDebug(5);
    view = model.snapshot();

    expect(view.visibleItems).toHaveLength(0);
    expect(view.blockedReason).toBe("no_active_memories");
    expect(view.auditSummary[0]).toMatchObject({
      action: "debug",
      result: "blocked",
      reason: "no_active_memories",
    });
    expect(bridge.requests.map((item) => item.command)).toEqual([
      "/memory preview --from-last-turn --type project",
      "/memory save --from-last-turn --scope project --type project",
      "/memory save --from-last-turn --scope project --type project",
      "/memory list --limit 20 --scope project --type project --status active",
      "/memory show mem_e2e_1 --scope project",
      "/memory debug --limit 5",
      "/memory delete mem_e2e_1",
      "/memory delete mem_e2e_2",
      "/memory list --limit 20 --scope project --type project --status active",
      "/memory debug --limit 5",
    ]);
  });

  it("parses memory debug explainability and blocked reason", async () => {
    const bridge = new ScriptedMemoryBridge((request) => {
      if (request.action !== "debug") {
        return { ok: false, text: "unexpected action", error: "unexpected action" };
      }
      return {
        ok: true,
        text: [
          "recalled_memory_count=1",
          "snapshot_recalled_count=1",
          "snapshot_recalled_ids=mem_alpha",
          "snapshot_blocked_reason=no_active_memories",
          "snapshot_query_paths=service/api.py",
          "snapshot_recalled_types=reference",
          "snapshot_ranking_explainability_count=1",
          "# rank=1 | memory_id=mem_alpha | type=reference | score=5.5 | selected=true | reasons=path_overlap,tag_overlap",
        ].join("\n"),
      };
    });

    const model = new MemoryManagementModel(bridge, () => "2026-04-09T10:03:00Z", "test.operator");
    await model.refreshDebug(5);

    const view = model.snapshot();
    expect(bridge.requests[0]?.command).toBe("/memory debug --limit 5");
    expect(view.blockedReason).toBe("no_active_memories");
    expect(view.explainability).toHaveLength(1);
    expect(view.explainability[0]).toMatchObject({
      rank: 1,
      memory_id: "mem_alpha",
      memory_type: "reference",
      score: 5.5,
      selected: true,
    });
    expect(view.explainability[0]?.reasons).toEqual(["path_overlap", "tag_overlap"]);
  });
});
