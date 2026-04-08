export {
  registerOTel,
  createLemmaSpanProcessor,
  type LemmaOTelOptions,
  type RegisterOTelOptions,
  type CreateLemmaSpanProcessorOptions,
} from "./register";
export {
  enableExperimentMode,
  disableExperimentMode,
  isExperimentModeEnabled,
} from "./experiment-mode";
export {
  enableDebugMode,
  disableDebugMode,
  isDebugModeEnabled,
} from "./debug-mode";
export {
  agent,
  wrapAgent, // @deprecated — use agent instead
  type TraceContext,
  type WrapAgentOptions,
  type WrapRunOptions,
} from "./trace-wrapper";
export {
  trace,
  tool,
  llm,
  retrieval,
} from "./span-helpers";
