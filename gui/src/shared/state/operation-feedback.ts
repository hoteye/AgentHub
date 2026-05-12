import type { BridgeResponse } from "../types/bridge.ts";

export type FeedbackLevel = "neutral" | "success" | "warning" | "error";

export type OperationFeedback = {
  level: FeedbackLevel;
  message: string;
};

type BridgeFeedbackOptions = {
  successMessage: string;
  errorMessage: string;
};

export function neutralFeedback(message: string): OperationFeedback {
  return { level: "neutral", message };
}

export function successFeedback(message: string): OperationFeedback {
  return { level: "success", message };
}

export function warningFeedback(message: string): OperationFeedback {
  return { level: "warning", message };
}

export function errorFeedback(message: string): OperationFeedback {
  return { level: "error", message };
}

export function feedbackFromBridgeResponse(
  response: BridgeResponse<unknown>,
  options: BridgeFeedbackOptions,
): OperationFeedback {
  if (response.ok) {
    return successFeedback(options.successMessage);
  }
  return errorFeedback(response.error?.message ?? options.errorMessage);
}
