import type { BridgeResponse } from "../types/bridge.ts";

export type HealthLevel = "ready" | "warning" | "error";

export type HealthSummary = {
  level: HealthLevel;
  detail: string;
  total: number;
  readyCount: number;
  warningCount: number;
  errorCount: number;
  failed: boolean;
};

type SummarizeCollectionOptions = {
  label: string;
  emptyDetail: string;
  failureDetail?: string;
  fallback?: HealthLevel;
};

const DEFAULT_FALLBACK: HealthLevel = "warning";

export function aggregateHealthLevels(
  levels: Array<string | null | undefined>,
  fallback: HealthLevel = DEFAULT_FALLBACK,
): HealthLevel {
  const normalized = levels
    .map((item) => normalizeHealthLevel(item))
    .filter((item): item is HealthLevel => item !== null);
  if (!normalized.length) {
    return fallback;
  }
  if (normalized.some((item) => item === "error")) {
    return "error";
  }
  if (normalized.every((item) => item === "ready")) {
    return "ready";
  }
  return "warning";
}

export function summarizeCollectionHealth(
  levels: Array<string | null | undefined>,
  options: SummarizeCollectionOptions,
): HealthSummary {
  const fallback = options.fallback ?? DEFAULT_FALLBACK;
  const normalized = levels
    .map((item) => normalizeHealthLevel(item))
    .filter((item): item is HealthLevel => item !== null);
  const total = normalized.length;
  const readyCount = normalized.filter((item) => item === "ready").length;
  const warningCount = normalized.filter((item) => item === "warning").length;
  const errorCount = normalized.filter((item) => item === "error").length;
  const level = aggregateHealthLevels(normalized, fallback);

  if (!total) {
    return {
      level: fallback,
      detail: options.emptyDetail,
      total,
      readyCount,
      warningCount,
      errorCount,
      failed: false,
    };
  }

  if (level === "error") {
    return {
      level,
      detail: `${readyCount}/${total} ${options.label}就绪，${errorCount} 错误`,
      total,
      readyCount,
      warningCount,
      errorCount,
      failed: false,
    };
  }

  if (level === "warning") {
    return {
      level,
      detail: `${readyCount}/${total} ${options.label}就绪，${warningCount} 降级`,
      total,
      readyCount,
      warningCount,
      errorCount,
      failed: false,
    };
  }

  return {
    level,
    detail: `${readyCount}/${total} ${options.label}就绪`,
    total,
    readyCount,
    warningCount,
    errorCount,
    failed: false,
  };
}

export function summarizeBridgeCollection<TItem>(
  response: BridgeResponse<unknown>,
  items: TItem[],
  getLevel: (item: TItem) => string | null | undefined,
  options: SummarizeCollectionOptions,
): HealthSummary {
  if (!response.ok) {
    return {
      level: "error",
      detail: response.error?.message ?? options.failureDetail ?? `${options.label}状态获取失败`,
      total: 0,
      readyCount: 0,
      warningCount: 0,
      errorCount: 1,
      failed: true,
    };
  }
  return summarizeCollectionHealth(items.map((item) => getLevel(item)), options);
}

function normalizeHealthLevel(value: string | null | undefined): HealthLevel | null {
  if (value === "ready" || value === "warning" || value === "error") {
    return value;
  }
  return null;
}
