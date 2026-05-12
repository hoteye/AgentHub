import type { BridgeClient } from "../../bridge/client.ts";
import type {
  ApprovalSummary,
  BridgeEvent,
  PluginSummary,
  SystemStatusSummary,
} from "../types/bridge.ts";

export type AppStateSnapshot = {
  system: SystemStatusSummary;
  lastEvent: BridgeEvent<Record<string, unknown>> | null;
  runningTaskCount: number;
  pendingApprovals: ApprovalSummary[];
  plugins: PluginSummary[];
};

type StateListener = (snapshot: AppStateSnapshot) => void;

export function createInitialAppState(): AppStateSnapshot {
  return {
    system: {
      model: "ready",
      browser: "warning",
      plugins: "warning",
      connectors: "warning",
    },
    lastEvent: null,
    runningTaskCount: 0,
    pendingApprovals: [],
    plugins: [],
  };
}

export class AppStateStore {
  private snapshot: AppStateSnapshot = createInitialAppState();
  private readonly listeners = new Set<StateListener>();

  getSnapshot(): AppStateSnapshot {
    return this.snapshot;
  }

  subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    return () => {
      this.listeners.delete(listener);
    };
  }

  replaceSnapshot(next: Partial<AppStateSnapshot>) {
    this.snapshot = {
      ...this.snapshot,
      ...next,
    };
    this.emit();
  }

  applyEvent(event: BridgeEvent<Record<string, unknown>>) {
    const next = { ...this.snapshot, lastEvent: event };
    switch (event.kind) {
      case "task_started":
        next.runningTaskCount += 1;
        break;
      case "task_completed":
      case "task_failed":
        next.runningTaskCount = Math.max(0, next.runningTaskCount - 1);
        break;
      case "approval_requested":
        if (event.payload.approval_id && event.payload.title && event.payload.trace_id) {
          next.pendingApprovals = [
            ...next.pendingApprovals,
            {
              approval_id: String(event.payload.approval_id),
              title: String(event.payload.title),
              trace_id: String(event.payload.trace_id),
              risk: "medium",
              status: "pending",
            },
          ];
        }
        break;
      case "approval_resolved":
        if (event.payload.approval_id) {
          next.pendingApprovals = next.pendingApprovals.filter(
            (item) => item.approval_id !== String(event.payload.approval_id),
          );
        }
        break;
      case "plugin_state_changed":
        next.system = {
          ...next.system,
          plugins: "ready",
        };
        break;
      case "browser_state_changed":
        next.system = {
          ...next.system,
          browser: "ready",
        };
        break;
      case "settings_changed":
        next.system = {
          ...next.system,
          model: "ready",
        };
        break;
      default:
        break;
    }
    this.snapshot = next;
    this.emit();
  }

  bindClient(client: BridgeClient): () => void {
    return client.subscribe((event) => this.applyEvent(event));
  }

  private emit() {
    for (const listener of this.listeners) {
      listener(this.snapshot);
    }
  }
}
