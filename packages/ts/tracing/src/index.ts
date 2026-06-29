export {
  Lemma,
  NoopSpanHandle,
  SpanHandle,
  TraceContext,
  TraceHandle,
  active,
  type DetachedGenerationOptions,
  type DetachedSpanOptions,
  type DetachedToolOptions,
  type GenerationOptions,
  type JsonValue,
  type LemmaClientOptions,
  type SpanOptions,
  type ToolOptions,
  type TraceEndOptions,
  type TraceOptions,
} from "./client";
export {
  disableDebugMode,
  enableDebugMode,
  isDebugModeEnabled,
  lemmaDebug,
} from "./debug-mode";
export {
  vercelAI,
  type LemmaVercelAIIntegrationOptions,
  type VercelAIIntegrationOptions,
  type VercelAITelemetryIntegration,
} from "./vercel-ai";
