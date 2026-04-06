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
  wrapAgent,
  type TraceContext,
  type WrapAgentOptions,
  type WrapRunOptions,
} from "./trace-wrapper";
