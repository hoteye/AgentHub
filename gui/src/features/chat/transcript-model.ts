import type { StoredActivityEvent, ThreadTurn } from "../../shared/types/bridge.ts";

export type TranscriptRenderEntry = {
  kind: "user" | "commentary" | "assistant" | "activity";
  layer: "user" | "commentary" | "tool" | "web" | "final";
  lines: string[];
  status?: string;
};

export function buildTranscriptEntries(turns: ThreadTurn[]): TranscriptRenderEntry[] {
  const entries: TranscriptRenderEntry[] = [];
  for (const turn of turns) {
    const userText = String(turn.user_text ?? "").trim();
    const commentaryText = String(turn.commentary_text ?? "").trim();
    const assistantText = String(turn.assistant_text ?? "").trim();
    if (userText) {
      entries.push({
        kind: "user",
        layer: "user",
        lines: formatTranscriptBlock(userText, "> ", "  "),
      });
    }
    if (commentaryText) {
      entries.push({
        kind: "commentary",
        layer: "commentary",
        lines: formatTranscriptBlock(commentaryText, "• ", "  "),
      });
    }
    for (const event of turn.activity_events ?? []) {
      const entry = activityEntry(event);
      if (entry) {
        entries.push(entry);
      }
    }
    if (assistantText) {
      entries.push({
        kind: "assistant",
        layer: "final",
        lines: formatTranscriptBlock(assistantText, "• ", "  "),
      });
    }
  }
  return entries;
}

export function formatTranscriptBlock(content: string, firstPrefix: string, continuationPrefix: string): string[] {
  const rawLines = String(content || "").split(/\r?\n/);
  return (rawLines.length ? rawLines : [""]).map((line, index) =>
    `${index === 0 ? firstPrefix : continuationPrefix}${line}`,
  );
}

export function activityEntry(event: StoredActivityEvent): TranscriptRenderEntry | null {
  const detail = normalizedActivityDetail(event);
  const lines = formatActivityLines({ ...event, detail });
  if (!lines.length) {
    return null;
  }
  const layer = event.kind === "web" ? "web" : event.kind === "tool" || event.kind === "command" ? "tool" : "commentary";
  return {
    kind: "activity",
    layer,
    lines,
    status: event.status,
  };
}

export function formatActivityLines(event: StoredActivityEvent): string[] {
  const summary = formatActivitySummary(event);
  const raw = String(event.detail || "").trim();
  if (!summary) {
    return raw ? formatActivityDetailLines(raw) : [];
  }
  if (!raw) {
    return [summary];
  }
  const title = String(event.title || "").trim();
  if (event.kind === "browser") {
    return appendBrowserSegments([summary], browserDetailSegments(raw));
  }
  if (event.kind === "web") {
    return [summary, ...formatActivityDetailLines(raw)];
  }
  if (title === "Applied patch" || title === "Requested patch approval" || title === "Requested shell approval") {
    return [summary, ...formatActivityDetailLines(raw)];
  }
  return [summary, ...formatActivityDetailLines(raw)];
}

export function formatActivitySummary(event: StoredActivityEvent): string {
  const title = String(event.title || "").trim();
  const marker = event.status === "error" ? "✗" : "•";
  if (event.kind === "interrupt") {
    return `• ${title || "Execution interrupted"}`;
  }
  if (event.kind === "command") {
    if (event.status === "running") {
      return `• Running ${stripActivityPrefix(title, "Running ") || "command"}`;
    }
    if (event.status === "success") {
      return `• Ran ${stripActivityPrefix(title, "Ran ") || "command"}`;
    }
    if (event.status === "error") {
      return `✗ ${title || "Command failed"}`;
    }
  }
  if (event.kind === "tool" && event.status === "running") {
    return `• Running ${stripActivityPrefix(title, "Running ") || "tool"}`;
  }
  if (event.status === "running") {
    return `• Running ${stripActivityPrefix(title, "Running ") || "activity"}`;
  }
  return title ? `${marker} ${title}` : "";
}

export function formatActivityDetailLines(detail: string): string[] {
  const rawLines = String(detail || "")
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.trim());
  if (!rawLines.length) {
    return [];
  }
  const [first, ...rest] = rawLines;
  return [`  └ ${first}`, ...rest.map((line) => `    ${line}`)];
}

function normalizedActivityDetail(event: StoredActivityEvent): string {
  const raw = String(event.detail || "").trim();
  if (!raw) {
    return "";
  }
  if (event.status === "error") {
    return raw;
  }
  const title = String(event.title || "").trim();
  if (event.kind === "command" && event.status === "success") {
    return "";
  }
  if (title.startsWith("Read recent messages from ")) {
    return "";
  }
  if (title.startsWith("Summarized ")) {
    return "";
  }
  if (title.startsWith("Drafted reply for ")) {
    return "";
  }
  return raw;
}

function stripActivityPrefix(title: string, prefix: string): string {
  const value = title.trim();
  return value.toLowerCase().startsWith(prefix.toLowerCase()) ? value.slice(prefix.length).trim() : value;
}

function browserDetailSegments(raw: string): string[] {
  const segments: string[] = [];
  for (const rawLine of raw.split(/\r?\n/)) {
    for (const segment of rawLine.split(" | ")) {
      const text = segment.trim();
      if (text) {
        segments.push(text);
      }
    }
  }
  return segments;
}

function appendBrowserSegments(lines: string[], segments: string[]): string[] {
  if (!segments.length) {
    return lines;
  }
  const [first, ...rest] = segments;
  return [...lines, `  └ ${first}`, ...rest.map((segment) => `    ${segment}`)];
}
